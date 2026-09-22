import os
import django
import random
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

# Initialize Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sweetbox_backend.settings')
django.setup()

from django.db import transaction
from accounts.models import Branch, User
from pos.models import ProductCategory, Product, Transaction, TransactionItem, PaymentRecord
from inventory.models import Ingredient, IngredientStock, ProductStock, BillOfMaterial, ConstraintParameter

@transaction.atomic
def seed_database():
    print("Clearing existing data...")
    Transaction.objects.all().delete()
    BillOfMaterial.objects.all().delete()
    IngredientStock.objects.all().delete()
    Product.objects.all().delete()
    ProductCategory.objects.all().delete()
    Ingredient.objects.all().delete()
    User.objects.all().delete()
    Branch.objects.all().delete()

    print("Seeding Branches...")
    branch_names = [
        "Ibaan (Main Hub)", "Padre Garcia", "San Jose", 
        "Sampaguita Lipa", "South Supermarket Lipa", 
        "San Antonio Quezon", "Cuenca"
    ]
    branches = []
    for name in branch_names:
        is_main = True if "Ibaan" in name else False
        branch = Branch.objects.create(name=name, address=f"Address for {name}", main_hub=is_main)
        branches.append(branch)

    print("Seeding Users...")
    owner = User.objects.create_user(
        email="owner@sweetbox.ph", password="password123", 
        name="Sheryll Ann P. Javier", role="Business Owner"
    )
    
    front_staff_users = []
    for branch in branches:
        # Create Branch Managers and Inventory Staff for future use
        User.objects.create_user(
            email=f"manager_{branch.branch_ID}@sweetbox.ph", password="password123",
            name=f"Manager {branch.name}", role="Branch Manager", branch=branch
        )
        User.objects.create_user(
            email=f"inv_{branch.branch_ID}@sweetbox.ph", password="password123",
            name=f"Inv Staff {branch.name}", role="Inventory Staff", branch=branch
        )
        # Create Front Staff for POS transactions
        staff = User.objects.create_user(
            email=f"staff_{branch.branch_ID}@sweetbox.ph", password="password123",
            name=f"Front Staff {branch.name}", role="Front Staff", branch=branch
        )
        front_staff_users.append(staff)

    print("Seeding Product Categories...")
    cat_cakes = ProductCategory.objects.create(category_name="Cakes", description="Whole and sliced cakes")
    cat_pastries = ProductCategory.objects.create(category_name="Pastries", description="Baked pastries")
    cat_drinks = ProductCategory.objects.create(category_name="Drinks", description="Cold and hot beverages")

    print("Seeding Products...")
    products_data = [
        (cat_cakes, "Chocolate Truffle Cake", 500.00),
        (cat_cakes, "Ube Chiffon Cake", 500.00),
        (cat_pastries, "Classic Ensaymada", 150.00),
        (cat_pastries, "Cheese Crinkles", 100.00),
        (cat_pastries, "Leche Flan", 120.00),
        (cat_drinks, "Strawberry Milkshake", 150.00),
        (cat_drinks, "Café Latte", 120.00)
    ]
    
    products = {}
    for cat, name, price in products_data:
        prod = Product.objects.create(category=cat, product_name=name, price=Decimal(str(price)))
        products[name] = prod

    print("Seeding Ingredients...")
    ingredients_data = [
        ("All-Purpose Flour", "kg", 50.00),
        ("Refined Sugar", "kg", 60.00),
        ("Unsalted Butter", "kg", 200.00),
        ("Fresh Eggs", "tray", 250.00),
        ("Cocoa Powder", "kg", 300.00),
        ("Cream Cheese", "kg", 450.00),
        ("Coffee Beans", "kg", 500.00),
        ("Milk", "liter", 90.00)
    ]
    
    ingredients = {}
    for name, unit, cost in ingredients_data:
        ing = Ingredient.objects.create(ingredient_name=name, measurement_unit=unit, cost_per_unit=Decimal(str(cost)))
        ingredients[name] = ing

    print("Seeding Bill of Materials (BOM)...")
    # Chocolate Truffle Cake Recipe
    BillOfMaterial.objects.create(product=products["Chocolate Truffle Cake"], ingredient=ingredients["All-Purpose Flour"], quantity_required=0.5, measurement_unit="kg")
    BillOfMaterial.objects.create(product=products["Chocolate Truffle Cake"], ingredient=ingredients["Cocoa Powder"], quantity_required=0.2, measurement_unit="kg")
    BillOfMaterial.objects.create(product=products["Chocolate Truffle Cake"], ingredient=ingredients["Refined Sugar"], quantity_required=0.3, measurement_unit="kg")

    # Café Latte Recipe
    BillOfMaterial.objects.create(product=products["Café Latte"], ingredient=ingredients["Coffee Beans"], quantity_required=0.05, measurement_unit="kg")
    BillOfMaterial.objects.create(product=products["Café Latte"], ingredient=ingredients["Milk"], quantity_required=0.2, measurement_unit="liter")

    print("Seeding Initial Ingredient Stocks & Constraints per Branch...")
    for branch in branches:
        for ing_name, ing_obj in ingredients.items():
            # Initial heavy stock so transactions don't error out
            IngredientStock.objects.create(
                branch=branch, ingredient=ing_obj,
                total_cost=Decimal('5000.00'), quantity_available=Decimal('100.00'),
                reorder_threshold=Decimal('10.00')
            )
            # Add Constraint Parameters for the AI logic
            ConstraintParameter.objects.create(
                branch=branch, ingredient=ing_obj, lead_time_days=2,
                min_order_quantity=Decimal('5.00'), max_order_quantity=Decimal('50.00'),
                production_limit=Decimal('100.00'), capacity_limit=Decimal('200.00')
            )

    print("Simulating 30 Days of Transactions...")
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)
    
    payment_methods = ['Cash', 'GCash', 'Maya', 'Credit Card']
    total_txns = 0

    current_date = start_date
    while current_date <= end_date:
        for branch in branches:
            # Generate 5 to 15 transactions per branch per day
            daily_txns = random.randint(5, 15)
            staff_user = next((u for u in front_staff_users if u.branch == branch), None)
            
            for _ in range(daily_txns):
                # Pick 1 to 3 random products for the cart
                cart_items = random.sample(list(products.values()), random.randint(1, 3))
                subtotal = sum([item.price for item in cart_items])
                
                txn = Transaction.objects.create(
                    branch=branch, user=staff_user,
                    subtotal_amount=subtotal, total_amount=subtotal,
                    transaction_status='Completed'
                )
                
                # Override the auto_now_add date to simulate historical spread
                Transaction.objects.filter(transaction_ID=txn.transaction_ID).update(transaction_date=current_date)

                for prod in cart_items:
                    qty = random.randint(1, 3)
                    item_subtotal = prod.price * qty
                    
                    TransactionItem.objects.create(
                        transaction=txn, product=prod,
                        quantity=qty, unit_price=prod.price, subtotal=item_subtotal
                    )
                    
                    # Automated BOM Deduction
                    recipes = BillOfMaterial.objects.filter(product=prod)
                    for recipe in recipes:
                        deduction = recipe.quantity_required * qty
                        stock = IngredientStock.objects.get(branch=branch, ingredient=recipe.ingredient)
                        stock.quantity_available -= deduction
                        stock.save()
                
                PaymentRecord.objects.create(
                    transaction=txn, amount_paid=subtotal,
                    payment_method=random.choice(payment_methods)
                )
                total_txns += 1
                
        current_date += timedelta(days=1)

    print(f"Database Seeding Complete! Generated {total_txns} historical transactions across 30 days.")

if __name__ == '__main__':
    seed_database()