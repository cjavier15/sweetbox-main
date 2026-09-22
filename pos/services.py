from django.db import transaction
from decimal import Decimal
from inventory.models import BillOfMaterial, IngredientStock
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

    # 2. Process Items and Deduct BOM Ingredients
    for item in items_data:
        product = item['product']
        quantity_sold = item['quantity']
        unit_price = item['unit_price']

        # Save Transaction Item
        TransactionItem.objects.create(
            transaction=txn,
            product=product,
            quantity=quantity_sold,
            unit_price=unit_price,
            subtotal=unit_price * quantity_sold
        )

        # Retrieve BOM Recipe for the Product
        bom_recipes = BillOfMaterial.objects.filter(product=product)
        
        for recipe in bom_recipes:
            ingredient = recipe.ingredient
            # Base required amount (Recipe Quantity * Sold Amount)
            total_required = float(recipe.quantity_required) * quantity_sold
            
            stock_record = IngredientStock.objects.filter(branch=branch, ingredient=ingredient).first()
            
            if stock_record:
                recipe_unit = recipe.measurement_unit.lower()
                stock_unit = stock_record.ingredient.measurement_unit.lower()
                
                # Unit Auto-Conversion Dictionary (From -> To : Multiplier)
                conversion_rates = {
                    ('g', 'kg'): 0.001,
                    ('grams', 'kg'): 0.001,
                    ('kg', 'g'): 1000.0,
                    ('ml', 'l'): 0.001,
                    ('ml', 'liter'): 0.001,
                    ('l', 'ml'): 1000.0,
                    ('liter', 'ml'): 1000.0,
                }
                
                # Apply conversion if units mismatch, otherwise deduct as 1:1
                if recipe_unit != stock_unit:
                    multiplier = conversion_rates.get((recipe_unit, stock_unit), 1.0)
                    final_deduction = total_required * multiplier
                else:
                    final_deduction = total_required

                stock_record.quantity_available -= Decimal(str(final_deduction))
                stock_record.save()

    return txn