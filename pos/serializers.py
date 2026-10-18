from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from .models import ProductCategory, Product, Transaction, TransactionItem
from inventory.models import ProductStock, IngredientStock

def is_cake_or_pastry_prod(product):
    cat_name = (product.category.category_name if product.category else '').strip().lower()
    return any(k in cat_name for k in ['cake', 'pastry', 'pastries'])

def is_hub_branch(branch):
    if not branch:
        return False
    return bool(getattr(branch, 'main_hub', False) or getattr(branch, 'branch_ID', None) == 1 or 'ibaan' in getattr(branch, 'name', '').lower())

def convert_bom_to_ing_unit(req_qty, bom_unit, ing_unit):
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
            stock = ProductStock.objects.filter(branch=branch, product=obj).first()
            return int(stock.quantity_available) if stock else 0

        # Case B: Made-to-Order Meal or Drink at Ibaan Main Hub
        recipes = list(obj.bom_ingredients.select_related('ingredient').all())
        if not recipes:
            return 0

        min_servings = float('inf')
        now = timezone.now()

        for bom in recipes:
            ing = bom.ingredient
            ing_stock = IngredientStock.objects.filter(branch=branch, ingredient=ing).first()
            if not ing_stock or ing_stock.quantity_available <= 0:
                return 0
            if ing_stock.expiry_date and ing_stock.expiry_date <= now:
                return 0

            req_converted = convert_bom_to_ing_unit(bom.quantity_required, bom.measurement_unit, ing.measurement_unit)
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
        payment = obj.payments.first() # Uses the 'payments' related_name
        return payment.payment_method if payment else "N/A"