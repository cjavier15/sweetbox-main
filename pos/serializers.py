from rest_framework import serializers
from .models import ProductCategory, Product, Transaction, TransactionItem
from inventory.models import ProductStock

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    quantity_available = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['product_ID', 'category_name', 'product_name', 'price', 'is_active', 'quantity_available']

    def get_quantity_available(self, obj):
        request = self.context.get('request')
        if request and hasattr(request.user, 'branch') and request.user.branch:
            stock = ProductStock.objects.filter(branch=request.user.branch, product=obj).first()
            return stock.quantity_available if stock else 0
        return 0

class TransactionItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.product_name', read_only=True)

    class Meta:
        model = TransactionItem
        fields = ['product', 'product_name', 'quantity', 'unit_price', 'subtotal']

class TransactionSerializer(serializers.ModelSerializer):
    items = TransactionItemSerializer(many=True, read_only=True)
    # Expose the payment method associated with this transaction
    payment_method = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = ['transaction_ID', 'branch', 'subtotal_amount', 'discount_type', 
                  'discount_amount', 'total_amount', 'transaction_status', 
                  'transaction_date', 'items', 'payment_method']

    def get_payment_method(self, obj):
        payment = obj.payments.first() # Uses the 'payments' related_name
        return payment.payment_method if payment else "N/A"