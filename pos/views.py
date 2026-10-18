import re
from decimal import Decimal
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction as db_transaction
from inventory.models import ProductStock, IngredientStock, BillOfMaterial, StockAdjustment
from accounts.models import AuditLog
from .models import Product, Transaction, PaymentRecord, TransactionItem
from .serializers import ProductSerializer, TransactionSerializer

def is_cake_or_pastry_prod(product):
    cat_name = (product.category.category_name if product.category else '').strip().lower()
    return any(k in cat_name for k in ['cake', 'pastry', 'pastries'])

def is_hub_branch(branch):
    if not branch:
        return False
    return bool(getattr(branch, 'main_hub', False) or getattr(branch, 'branch_ID', None) == 1 or 'ibaan' in getattr(branch, 'name', '').lower())

def convert_to_ingredient_unit(req_qty, bom_unit, ing_unit):
    b_unit = (bom_unit or '').strip().lower()
    i_unit = (ing_unit or '').strip().lower()
    val = Decimal(str(req_qty))
    if b_unit == i_unit:
        return val
    if b_unit in ['g', 'grams'] and i_unit == 'kg':
        return val / Decimal('1000')
    if b_unit == 'kg' and i_unit in ['g', 'grams']:
        return val * Decimal('1000')
    if b_unit in ['ml', 'milliliters'] and i_unit in ['l', 'liter', 'liters']:
        return val / Decimal('1000')
    if b_unit in ['l', 'liter', 'liters'] and i_unit in ['ml', 'milliliters']:
        return val * Decimal('1000')
    return val

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
                ).select_related('category').distinct().order_by('product_name')

        return Product.objects.filter(is_active=True).select_related('category').order_by('product_name')

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
        ).order_by('-transaction_date')

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

            # 1. Create Transaction Record
            txn = Transaction.objects.create(
                branch=branch,
                user=user,
                subtotal_amount=calculated_subtotal,
                discount_type=data.get('discount_type', ''),
                discount_amount=discount_amount,
                total_amount=total_amount,
                transaction_status='Completed'
            )
            
            is_hub = is_hub_branch(branch)
            required_bom_ingredients = {}
            ingredient_products_map = {}
            now = timezone.now()

            # 2. Process Items and Analyze Requirements
            for item in items_data:
                product = Product.objects.select_related('category').get(product_ID=item['product_id'])
                quantity_sold = int(item['quantity'])
                unit_price = Decimal(str(item['unit_price']))
                
                TransactionItem.objects.create(
                    transaction=txn,
                    product=product,
                    quantity=quantity_sold,
                    unit_price=unit_price,
                    subtotal=unit_price * quantity_sold
                )

                is_cake_or_pastry = is_cake_or_pastry_prod(product)

                if not is_hub or is_cake_or_pastry:
                    # Finished Goods (Pre-made ProductStock)
                    stock_record = ProductStock.objects.select_for_update().filter(branch=branch, product=product).first()
                    if not stock_record or stock_record.quantity_available < quantity_sold:
                        avail = stock_record.quantity_available if stock_record else 0
                        raise ValueError(f"Insufficient stock for {product.product_name}. Only {avail} left in stock.")
                    
                    stock_record.quantity_available -= Decimal(str(quantity_sold))
                    stock_record.save()

                    StockAdjustment.objects.create(
                        user=user,
                        product_inventory=stock_record,
                        adjustment_type='Stock-out',
                        quantity_change=Decimal(str(quantity_sold)),
                        reason=f"POS Sale TXN-{txn.transaction_ID}"
                    )
                else:
                    # Made-to-Order Meal or Drink at Ibaan Main Hub: accumulate BOM ingredient deductions
                    bom_recipes = list(product.bom_ingredients.select_related('ingredient').all())
                    if not bom_recipes:
                        raise ValueError(f"No recipe (BOM) configured for made-to-order item '{product.product_name}'. Cannot prepare.")

                    for recipe in bom_recipes:
                        ing = recipe.ingredient
                        deduct_per_serving = convert_to_ingredient_unit(recipe.quantity_required, recipe.measurement_unit, ing.measurement_unit)
                        total_for_item = deduct_per_serving * Decimal(str(quantity_sold))

                        required_bom_ingredients[ing] = required_bom_ingredients.get(ing, Decimal('0.00')) + total_for_item
                        if ing not in ingredient_products_map:
                            ingredient_products_map[ing] = []
                        ingredient_products_map[ing].append(product.product_name)

            # 3. Validate and Deduct Made-to-Order BOM Ingredients at Ibaan Hub
            if required_bom_ingredients:
                for ing, total_needed in required_bom_ingredients.items():
                    ing_stock = IngredientStock.objects.select_for_update().filter(branch=branch, ingredient=ing).first()
                    prod_names = ", ".join(list(set(ingredient_products_map.get(ing, []))))
                    if not ing_stock:
                        raise ValueError(f"Insufficient or expired ingredient '{ing.ingredient_name}' for {prod_names} (Need {total_needed} {ing.measurement_unit}, Available 0 {ing.measurement_unit}).")
                    if ing_stock.expiry_date and ing_stock.expiry_date <= now:
                        raise ValueError(f"Insufficient or expired ingredient '{ing.ingredient_name}' for {prod_names} (Expired on {ing_stock.expiry_date.strftime('%Y-%m-%d')}).")
                    if ing_stock.quantity_available < total_needed:
                        raise ValueError(f"Insufficient or expired ingredient '{ing.ingredient_name}' for {prod_names} (Need {total_needed} {ing.measurement_unit}, Available {ing_stock.quantity_available} {ing.measurement_unit}).")

                for ing, total_needed in required_bom_ingredients.items():
                    ing_stock = IngredientStock.objects.select_for_update().filter(branch=branch, ingredient=ing).first()
                    if ing_stock.quantity_available > 0 and ing_stock.total_cost > 0:
                        cost_per_unit = ing_stock.total_cost / ing_stock.quantity_available
                        ing_stock.total_cost = max(Decimal('0.00'), ing_stock.total_cost - (cost_per_unit * total_needed))
                    ing_stock.quantity_available -= total_needed
                    ing_stock.save()

                    StockAdjustment.objects.create(
                        user=user,
                        ingredients_inventory=ing_stock,
                        adjustment_type='Stock-out',
                        quantity_change=total_needed,
                        reason=f"POS Made-to-Order Sale TXN-{txn.transaction_ID}"
                    )

            # 4. Record the Payment — store reference_number for E-Wallet/Split
            PaymentRecord.objects.create(
                transaction=txn,
                amount_paid=total_amount,
                payment_method=payment_method,
                reference_number=reference_number if reference_number else None
            )

            AuditLog.objects.create(
                user=user,
                action="Sale Transaction",
                module="POS",
                details=f"Processed TXN-{txn.transaction_ID} at {branch.name} totaling ₱{total_amount}"
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

                if not is_hub or is_cake_or_pastry:
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
                    # Restore raw ingredients to Ibaan IngredientStock
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