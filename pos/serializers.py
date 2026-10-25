from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from .models import ProductCategory, Product, Transaction, TransactionItem
from inventory.models import ProductStock, IngredientStock
from .services import (
    is_cake_or_pastry_prod,
    is_hub_branch,
    convert_to_ingredient_unit,
    convert_bom_to_ing_unit
)

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    quantity_available = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['product_ID', 'category_name', 'product_name', 'price', 'is_active', 'quantity_available']

    def get_quantity_available(self, obj):
        branch = None
        request = self.context.get('request')
        if request and hasattr(request.user, 'branch') and request.user.branch:
            branch = request.user.branch
        elif 'branch' in self.context and self.context['branch']:
            branch = self.context['branch']

        if not branch:
            return 0
        is_hub = is_hub_branch(branch)
        is_cp = is_cake_or_pastry_prod(obj)

        # Case A: Cake/Pastry at any branch, or any item at a Satellite Branch
        if is_cp or not is_hub:
            if 'product_stock_map' in self.context:
                return self.context['product_stock_map'].get(obj.product_ID, 0)
            stock = ProductStock.objects.filter(branch=branch, product=obj).first()
            return int(stock.quantity_available) if stock else 0

        # Case B: Made-to-Order Meal or Drink at Ibaan Main Hub
        recipes = list(obj.bom_ingredients.all())
        if not recipes:
            return 0

        min_servings = float('inf')
        now = timezone.now()
        ing_map = self.context.get('ingredient_stock_map')

        for bom in recipes:
            ing = bom.ingredient
            if ing_map is not None:
                ing_stock = ing_map.get(bom.ingredient_id)
            else:
                ing_stock = IngredientStock.objects.filter(branch=branch, ingredient=ing).first()

            if not ing_stock or ing_stock.quantity_available <= 0:
                return 0
            if ing_stock.expiry_date and ing_stock.expiry_date <= now:
                return 0

            req_converted = convert_to_ingredient_unit(bom.quantity_required, bom.measurement_unit, ing.measurement_unit)
            if req_converted <= Decimal('0.00'):
                continue

            servings = int(Decimal(str(ing_stock.quantity_available)) // req_converted)
            if servings <= 0:
                return 0

            if servings < min_servings:
                min_servings = servings

        return int(min_servings) if min_servings != float('inf') else 0

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
        payments = list(obj.payments.all())
        return payments[0].payment_method if payments else "N/A"
