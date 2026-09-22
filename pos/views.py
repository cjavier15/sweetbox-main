from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction as db_transaction
from inventory.models import ProductStock
from .models import Product, Transaction, PaymentRecord, TransactionItem
from .serializers import ProductSerializer, TransactionSerializer

class ProductListView(generics.ListAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

class TransactionListView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'Business Owner':
            return Transaction.objects.filter(
                transaction_status='Completed'
            ).order_by('-transaction_date')
            
        return Transaction.objects.filter(
            branch=user.branch, 
            transaction_status='Completed'
        ).order_by('-transaction_date')

class TransactionCreateView(APIView):
    permission_classes = [IsAuthenticated]
    
    @db_transaction.atomic
    def post(self, request):
        user = request.user
        branch = user.branch
        if not branch:
            return Response(
                {"error": "Only branch-assigned staff can process transactions."}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        data = request.data
        try:
            # 1. Create Transaction Record
            txn = Transaction.objects.create(
                branch=branch,
                user=user,
                subtotal_amount=data.get('total_amount', 0.00),
                discount_type=data.get('discount_type', ''),
                discount_amount=data.get('discount_amount', 0.00),
                total_amount=data.get('total_amount', 0.00),
                transaction_status='Completed'
            )
            
            # 2. Process Items and Deduct FINISHED ProductStock
            for item in data.get('items', []):
                product = Product.objects.get(product_ID=item['product_id'])
                quantity_sold = int(item['quantity'])
                unit_price = item['unit_price']
                
                TransactionItem.objects.create(
                    transaction=txn,
                    product=product,
                    quantity=quantity_sold,
                    unit_price=unit_price,
                    subtotal=float(unit_price) * quantity_sold
                )
                
                # Enforce Hub-to-Branch constraint: Deduct only finished goods
                stock_record = ProductStock.objects.filter(branch=branch, product=product).first()
                if stock_record:
                    if stock_record.quantity_available < quantity_sold:
                        raise ValueError(f"Insufficient stock for {product.product_name}.")
                    stock_record.quantity_available -= quantity_sold
                    stock_record.save()
                else:
                    raise ValueError(f"No active stock record for {product.product_name} at this branch.")
                    
            # 3. Record the Payment
            PaymentRecord.objects.create(
                transaction=txn,
                amount_paid=data.get('total_amount', 0.00),
                payment_method=data.get('payment_method', 'Cash')
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
        try:
            txn = Transaction.objects.get(transaction_ID=txn_id, branch=request.user.branch)
            
            # 1. Rollback Inventory (Add FINISHED products back to stock)
            for item in txn.items.all():
                stock = ProductStock.objects.filter(branch=txn.branch, product=item.product).first()
                if stock:
                    stock.quantity_available += item.quantity
                    stock.save()
                    
            # 2. Remove from Database
            txn.delete()
            return Response({"message": f"TXN-{txn_id} successfully refunded and removed."})
            
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)