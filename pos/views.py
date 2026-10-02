from decimal import Decimal
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction as db_transaction
from inventory.models import ProductStock
from accounts.models import AuditLog
from .models import Product, Transaction, PaymentRecord, TransactionItem
from .serializers import ProductSerializer, TransactionSerializer

class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role != 'Staff' and not user.is_superuser:
            return Product.objects.none()
        return Product.objects.filter(is_active=True)

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
            
            # 2. Process Items and Deduct FINISHED ProductStock
            for item in items_data:
                product = Product.objects.get(product_ID=item['product_id'])
                quantity_sold = int(item['quantity'])
                unit_price = Decimal(str(item['unit_price']))
                
                TransactionItem.objects.create(
                    transaction=txn,
                    product=product,
                    quantity=quantity_sold,
                    unit_price=unit_price,
                    subtotal=unit_price * quantity_sold
                )
                
                # Enforce Hub-to-Branch constraint: Deduct only finished goods
                stock_record, _ = ProductStock.objects.get_or_create(
                    branch=branch, product=product,
                    defaults={'quantity_available': Decimal('0.00'), 'reorder_threshold': Decimal('5.00')}
                )
                if Decimal(str(stock_record.quantity_available)) < Decimal(str(quantity_sold)):
                    raise ValueError(f"Insufficient stock for {product.product_name}. Only {stock_record.quantity_available} left in stock.")
                
                stock_record.quantity_available = Decimal(str(stock_record.quantity_available)) - Decimal(str(quantity_sold))
                stock_record.save()
                    
            # 3. Record the Payment
            PaymentRecord.objects.create(
                transaction=txn,
                amount_paid=total_amount,
                payment_method=data.get('payment_method', 'Cash')
            )

            AuditLog.objects.create(
                user=user,
                action="Sale Transaction",
                module="POS",
                details=f"Processed TXN-{txn.transaction_ID} at {branch.name} totaling ₱{total_amount}"
            )
            
            return Response(
                {"message": "Transaction successful. Finished goods deducted.", "transaction_ID": txn.transaction_ID}, 
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
                
            # 1. Rollback Inventory (Add FINISHED products back to stock)
            for item in txn.items.all():
                stock, _ = ProductStock.objects.get_or_create(
                    branch=txn.branch, product=item.product,
                    defaults={'quantity_available': Decimal('0.00'), 'reorder_threshold': Decimal('5.00')}
                )
                stock.quantity_available = Decimal(str(stock.quantity_available)) + Decimal(str(item.quantity))
                stock.save()
                    
            # 2. Mark as Refunded (Soft delete/status update to preserve audit integrity)
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