from django.db import transaction
from decimal import Decimal
from inventory.models import BillOfMaterial, IngredientStock, ProductStock
from pos.models import Transaction, TransactionItem

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

    is_hub = bool(branch and (branch.main_hub or branch.branch_ID == 1 or 'ibaan' in branch.name.lower()))

    # 2. Process Items and Deduct Inventory
    for item in items_data:
        product = item['product']
        quantity_sold = int(item['quantity'])
        unit_price = Decimal(str(item['unit_price']))

        # Save Transaction Item
        TransactionItem.objects.create(
            transaction=txn,
            product=product,
            quantity=quantity_sold,
            unit_price=unit_price,
            subtotal=unit_price * quantity_sold
        )

        cat_name = (product.category.category_name if product.category else '').strip().lower()
        is_cake_or_pastry = any(k in cat_name for k in ['cake', 'pastry', 'pastries'])

        # Satellite branches & Cake/Pastry products: Deduct strictly from finished ProductStock
        # (Raw materials were already deducted at Ibaan Commissary during ProduceProductView)
        stock_record, _ = ProductStock.objects.select_for_update().get_or_create(
            branch=branch, product=product,
            defaults={'quantity_available': Decimal('0.00'), 'reorder_threshold': Decimal('5.00')}
        )
        if Decimal(str(stock_record.quantity_available)) < Decimal(str(quantity_sold)):
            raise ValueError(f"Insufficient stock for {product.product_name}. Only {stock_record.quantity_available} left in stock.")

        stock_record.quantity_available = Decimal(str(stock_record.quantity_available)) - Decimal(str(quantity_sold))
        stock_record.save()

        # ONLY for Ibaan (Main Hub) made-to-order non-cake/pastry items: Deduct BOM raw ingredients
        if is_hub and not is_cake_or_pastry:
            bom_recipes = BillOfMaterial.objects.filter(product=product).select_related('ingredient')
            for recipe in bom_recipes:
                ingredient = recipe.ingredient
                total_required = float(recipe.quantity_required) * quantity_sold
                ing_stock = IngredientStock.objects.select_for_update().filter(branch=branch, ingredient=ingredient).first()
                if ing_stock:
                    recipe_unit = recipe.measurement_unit.lower()
                    stock_unit = ing_stock.ingredient.measurement_unit.lower()
                    conversion_rates = {
                        ('g', 'kg'): 0.001,
                        ('grams', 'kg'): 0.001,
                        ('kg', 'g'): 1000.0,
                        ('ml', 'l'): 0.001,
                        ('ml', 'liter'): 0.001,
                        ('l', 'ml'): 1000.0,
                        ('liter', 'ml'): 1000.0,
                    }
                    multiplier = conversion_rates.get((recipe_unit, stock_unit), 1.0) if recipe_unit != stock_unit else 1.0
                    final_deduction = Decimal(str(total_required * multiplier))
                    ing_stock.quantity_available -= final_deduction
                    ing_stock.save()

    return txn