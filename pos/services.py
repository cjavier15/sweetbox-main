from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from inventory.models import BillOfMaterial, IngredientStock, ProductStock, StockAdjustment
from accounts.models import AuditLog
from pos.models import Transaction, TransactionItem, Product, PaymentRecord

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

# Alias for backward-compatibility
convert_bom_to_ing_unit = convert_to_ingredient_unit

@transaction.atomic
def process_pos_transaction(branch, user, items_data, payment_data, subtotal, discount_type, discount_amount, total):
    # 1. Create Transaction Record
    txn = Transaction.objects.create(
        branch=branch,
        user=user,
        subtotal_amount=subtotal,
        discount_type=discount_type,
        discount_amount=discount_amount,
        total_amount=total,
        transaction_status='Completed'
    )

    is_hub = is_hub_branch(branch)
    required_bom_ingredients = {}
    ingredient_products_map = {}
    now = timezone.now()

    # 2. Process Items and Analyze Requirements
    for item in items_data:
        prod_val = item.get('product') if 'product' in item else item.get('product_id')
        product = prod_val if isinstance(prod_val, Product) else Product.objects.select_related('category').get(product_ID=prod_val)
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

        if is_cake_or_pastry:
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
            # Made-to-Order Meal or Drink: accumulate BOM raw ingredient deductions
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

    # 3. Validate and Deduct Made-to-Order BOM Ingredients at Branch
    if required_bom_ingredients:
        # Step A: Lock and verify all required ingredients under select_for_update
        for ing, total_needed in required_bom_ingredients.items():
            ing_stock = IngredientStock.objects.select_for_update().filter(branch=branch, ingredient=ing).first()
            prod_names = ", ".join(list(set(ingredient_products_map.get(ing, []))))
            if not ing_stock:
                raise ValueError(f"Insufficient or expired ingredient '{ing.ingredient_name}' for {prod_names} (Need {total_needed} {ing.measurement_unit}, Available 0 {ing.measurement_unit}).")
            if ing_stock.expiry_date and ing_stock.expiry_date <= now:
                raise ValueError(f"Insufficient or expired ingredient '{ing.ingredient_name}' for {prod_names} (Expired on {ing_stock.expiry_date.strftime('%Y-%m-%d')}).")
            if ing_stock.quantity_available < total_needed:
                raise ValueError(f"Insufficient or expired ingredient '{ing.ingredient_name}' for {prod_names} (Need {total_needed} {ing.measurement_unit}, Available {ing_stock.quantity_available} {ing.measurement_unit}).")

        # Step B: Apply deductions to IngredientStock
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

    # 4. Record the Payment & Audit Log
    if isinstance(payment_data, dict):
        pm_method = payment_data.get('payment_method', 'Cash')
        ref_num = payment_data.get('reference_number')
    else:
        pm_method = str(payment_data) if payment_data else 'Cash'
        ref_num = None

    PaymentRecord.objects.create(
        transaction=txn,
        amount_paid=total,
        payment_method=pm_method,
        reference_number=ref_num if ref_num else None
    )

    AuditLog.objects.create(
        user=user,
        action="Sale Transaction",
        module="POS",
        details=f"Processed TXN-{txn.transaction_ID} at {branch.name} totaling ₱{total}"
    )

    return txn
