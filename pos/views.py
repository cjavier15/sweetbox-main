import re
from decimal import Decimal
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction as db_transaction
from inventory.models import ProductStock, IngredientStock, StockAdjustment
from accounts.models import AuditLog
from .models import Product, Transaction, PaymentRecord, TransactionItem
from .serializers import ProductSerializer, TransactionSerializer
from .services import (
    is_cake_or_pastry_prod,
    is_hub_branch,
    convert_to_ingredient_unit,
    process_pos_transaction
)

class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role != 'Staff' and not user.is_superuser:
            return Product.objects.none()

        branch = user.branch
        if branch:
            is_hub = is_hub_branch(branch)
            if is_hub:
                # Ibaan (Main Hub): return ALL active products with prefetch
                return Product.objects.filter(
                    is_active=True
                ).select_related('category').prefetch_related('bom_ingredients__ingredient').order_by('product_name')
            else:
                # Satellite Branch: return only products assigned in this satellite branch's ProductStock
                return Product.objects.filter(
                    is_active=True,
                    stocks__branch=branch
                ).select_related('category').prefetch_related('bom_ingredients__ingredient').distinct().order_by('product_name')

        return Product.objects.filter(is_active=True).select_related('category').prefetch_related('bom_ingredients__ingredient').order_by('product_name')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        branch = getattr(user, 'branch', None)
        if branch:
            context['branch'] = branch
            context['product_stock_map'] = {
                ps.product_id: int(ps.quantity_available)
                for ps in ProductStock.objects.filter(branch=branch)
            }
            context['ingredient_stock_map'] = {
                ist.ingredient_id: ist
                for ist in IngredientStock.objects.filter(branch=branch)
            }
        return context

class TransactionListView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.role != 'Staff' and not user.is_superuser:
            return Transaction.objects.none()
            
        return Transaction.objects.filter(
            branch=user.branch, 
            transaction_status='Completed'
        ).prefetch_related('items__product', 'payments').order_by('-transaction_date')[:100]

class TransactionCreateView(APIView):
    permission_classes = [IsAuthenticated]
    
    @db_transaction.atomic
    def post(self, request):
        user = request.user
        if user.role != 'Staff' and not user.is_superuser:
            return Response(
                {"error": "Access denied. Only Staff can process transactions."}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        branch = user.branch
        if not branch:
            return Response(
                {"error": "Only branch-assigned staff can process transactions."}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        data = request.data
        try:
            items_data = data.get('items', [])
            if not items_data:
                return Response({"error": "No items provided for transaction."}, status=status.HTTP_400_BAD_REQUEST)

            # Calculate accurate subtotal from line items
            calculated_subtotal = Decimal('0.00')
            for item in items_data:
                qty = int(item['quantity'])
                price = Decimal(str(item['unit_price']))
                calculated_subtotal += (price * qty)

            discount_amount = Decimal(str(data.get('discount_amount', '0.00')))
            total_amount = Decimal(str(data['total_amount'])) if 'total_amount' in data else (calculated_subtotal - discount_amount)

            # --- E-Wallet Reference Number Validation ---
            payment_method = data.get('payment_method', 'Cash')
            reference_number = str(data.get('reference_number', '') or '').strip()

            if payment_method in ('E-Wallet', 'Split Payment'):
                if not reference_number:
                    return Response(
                        {"error": "An E-Wallet reference number is required for this payment method."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if not re.fullmatch(r'^\d{13}$', reference_number):
                    return Response(
                        {"error": "E-Wallet reference number must be exactly 13 digits (numbers only)."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            txn = process_pos_transaction(
                branch=branch,
                user=user,
                items_data=items_data,
                payment_data={'payment_method': payment_method, 'reference_number': reference_number},
                subtotal=calculated_subtotal,
                discount_type=data.get('discount_type', ''),
                discount_amount=discount_amount,
                total=total_amount
            )

            return Response(
                {"message": "Transaction successful. Inventory deducted.", "transaction_ID": txn.transaction_ID}, 
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class TransactionRefundView(APIView):
    permission_classes = [IsAuthenticated]
    
    @db_transaction.atomic
    def delete(self, request, txn_id):
        if request.user.role != 'Staff' and not request.user.is_superuser:
            return Response(
                {"error": "Access denied. Only Staff can process refunds."}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        try:
            txn = Transaction.objects.get(transaction_ID=txn_id, branch=request.user.branch)
            if txn.transaction_status == 'Refunded':
                return Response({"error": "Transaction has already been refunded."}, status=status.HTTP_400_BAD_REQUEST)
                
            is_hub = is_hub_branch(txn.branch)

            # 1. Rollback Inventory
            for item in txn.items.select_related('product__category').all():
                product = item.product
                is_cake_or_pastry = is_cake_or_pastry_prod(product)

                if is_cake_or_pastry:
                    # Restore finished ProductStock
                    stock, _ = ProductStock.objects.select_for_update().get_or_create(
                        branch=txn.branch, product=product,
                        defaults={'quantity_available': Decimal('0.00'), 'reorder_threshold': Decimal('5.00')}
                    )
                    stock.quantity_available += Decimal(str(item.quantity))
                    stock.save()

                    StockAdjustment.objects.create(
                        user=request.user,
                        product_inventory=stock,
                        adjustment_type='Stock-in',
                        quantity_change=Decimal(str(item.quantity)),
                        reason=f"POS Refund TXN-{txn.transaction_ID}"
                    )
                else:
                    # Restore raw ingredients to IngredientStock at branch
                    boms = list(product.bom_ingredients.select_related('ingredient').all())
                    for bom in boms:
                        ing = bom.ingredient
                        deduct_per_serving = convert_to_ingredient_unit(bom.quantity_required, bom.measurement_unit, ing.measurement_unit)
                        restore_qty = deduct_per_serving * Decimal(str(item.quantity))

                        ing_stock, _ = IngredientStock.objects.select_for_update().get_or_create(
                            branch=txn.branch, ingredient=ing,
                            defaults={'quantity_available': Decimal('0.00'), 'total_cost': Decimal('0.00'), 'reorder_threshold': Decimal('10.00')}
                        )
                        ing_stock.quantity_available += restore_qty
                        ing_stock.total_cost += round(ing.cost_per_unit * restore_qty, 2)
                        ing_stock.save()

                        StockAdjustment.objects.create(
                            user=request.user,
                            ingredients_inventory=ing_stock,
                            adjustment_type='Stock-in',
                            quantity_change=restore_qty,
                            reason=f"POS Refund TXN-{txn.transaction_ID}"
                        )
                    
            # 2. Mark as Refunded
            txn.transaction_status = 'Refunded'
            txn.save()

            AuditLog.objects.create(
                user=request.user,
                action="Refund",
                module="POS",
                details=f"Refunded transaction TXN-{txn_id} totaling ₱{txn.total_amount}"
            )
            return Response({"message": f"TXN-{txn_id} successfully refunded."})
            
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
