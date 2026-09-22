import random
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import Branch
from pos.models import Product, ProductCategory, Transaction, TransactionItem, PaymentRecord
from inventory.models import Ingredient, BillOfMaterial, IngredientStock, ProductStock, RestockRequest, ConstraintParameter
from analytics.models import PrescriptiveOutput

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with full RBAC accounts, products, inventory, historical sales, and pending AI tasks.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding database with full mock environment...")
        
        # 1. Establish Branches
        branch_names = [
            'Ibaan (Main Hub)', 'Padre Garcia', 'San Jose', 
            'Sampaguita', 'South Supermarket Lipa', 'San Antonio Quezon', 'Cuenca'
        ]
        branches = {name: Branch.objects.get_or_create(name=name)[0] for name in branch_names}
        main_hub = branches['Ibaan (Main Hub)']
        main_hub.main_hub = True
        main_hub.save()

        # 2. Establish Branch-Specific RBAC Accounts
        for i, name in enumerate(branch_names):
            idx = i + 1
            branch = branches[name]
            
            # Staff (POS)
            staff, _ = User.objects.get_or_create(email=f"staff_{idx}@sweetbox.ph")
            staff.set_password('sweetbox123')
            staff.name = f"{name} Cashier"
            staff.role = 'Staff'
            staff.branch = branch
            staff.save()

            # Branch Manager (Strictly SCM/Inventory)
            mgr, _ = User.objects.get_or_create(email=f"manager_{idx}@sweetbox.ph")
            mgr.set_password('sweetbox123')
            mgr.name = f"{name} Manager"
            mgr.role = 'Branch Manager'
            mgr.branch = branch
            mgr.save()

        # Global Owner (Enterprise, SCM, Approvals)
        owner, _ = User.objects.get_or_create(email="owner@sweetbox.ph")
        owner.set_password('sweetbox123')
        owner.name = "Business Owner"
        owner.role = 'Business Owner'
        owner.branch = main_hub
        owner.save()
        
        # Dedicated Admin (Privileges and Accounts only)
        admin_user, _ = User.objects.get_or_create(email="admin@sweetbox.ph")
        admin_user.set_password('sweetbox123')
        admin_user.name = "System Administrator"
        admin_user.role = 'Admin'
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save()

        # 3. Expanded Categories & Products
        cat_cakes, _ = ProductCategory.objects.get_or_create(category_name="Cakes")
        cat_pastries, _ = ProductCategory.objects.get_or_create(category_name="Pastries")
        cat_coffee, _ = ProductCategory.objects.get_or_create(category_name="Coffee")
        
        products_data = [
            ("Chocolate Truffle Cake", cat_cakes, 650.00), ("Ube Chiffon Cake", cat_cakes, 550.00),
            ("Mango Bravo", cat_cakes, 850.00), ("Red Velvet Cake", cat_cakes, 700.00),
            ("Classic Ensaymada", cat_pastries, 85.00), ("Leche Flan", cat_pastries, 150.00),
            ("Cheese Crinkles", cat_pastries, 120.00), ("Fudge Brownies", cat_pastries, 180.00),
            ("Cafe Latte", cat_coffee, 120.00), ("Iced Caramel Macchiato", cat_coffee, 150.00),
            ("Americano", cat_coffee, 100.00)
        ]
        
        products = {}
        product_list = []
        for p_name, cat, price in products_data:
            p, _ = Product.objects.get_or_create(product_name=p_name, defaults={'category': cat, 'price': price, 'is_active': True})
            products[p_name] = p
            product_list.append(p)

        # 4. Expanded Ingredients
        ingredients_data = [
            ("All-Purpose Flour", "kg", 60.00), ("Refined Sugar", "kg", 80.00),
            ("Cocoa Powder", "kg", 250.00), ("Unsalted Butter", "kg", 350.00),
            ("Fresh Eggs", "tray", 220.00), ("Cream Cheese", "kg", 450.00),
            ("Coffee Beans", "kg", 600.00), ("Milk", "L", 95.00),
            ("Vanilla Extract", "L", 800.00), ("Fresh Mangoes", "kg", 150.00),
            ("Chocolate Chips", "kg", 320.00), ("Caramel Syrup", "L", 250.00)
        ]
        
        ingredients = {}
        for i_name, unit, cost in ingredients_data:
            ing, _ = Ingredient.objects.get_or_create(ingredient_name=i_name, defaults={'measurement_unit': unit, 'cost_per_unit': cost})
            ingredients[i_name] = ing

        # 5. Distribute Dynamic Inventory & Constraints
        now = timezone.now()
        
        for branch_name, branch in branches.items():
            for ing_name, ing in ingredients.items():
                qty = random.choice([2, 4, 15, 25, 50])
                days_to_expiry = random.choice([5, 12, 45, 90, None])
                expiry = (now + timedelta(days=days_to_expiry)) if days_to_expiry else None
                
                IngredientStock.objects.update_or_create(
                    branch=branch, ingredient=ing,
                    defaults={
                        'quantity_available': qty, 
                        'reorder_threshold': 10, 
                        'total_cost': qty * ing.cost_per_unit,
                        'expiry_date': expiry
                    }
                )
                
                ConstraintParameter.objects.update_or_create(
                    branch=branch, ingredient=ing,
                    defaults={
                        'lead_time_days': 2,
                        'min_order_quantity': 5.00,
                        'max_order_quantity': 100.00,
                        'production_limit': 50.00,
                        'capacity_limit': 200.00
                    }
                )
                
            for p_name, prod in products.items():
                qty = random.choice([0, 2, 8, 15])
                ProductStock.objects.update_or_create(
                    branch=branch, product=prod,
                    defaults={'quantity_available': qty, 'low_stock_threshold': 5, 'total_cost': 0, 'reorder_threshold': 5}
                )

        # 6. Generate Mock POS Transactions for Charts
        payment_methods = ['Cash', 'GCash', 'Maya', 'Split Payment']
        for branch in branches.values():
            staff = User.objects.filter(branch=branch, role='Staff').first()
            for _ in range(15): # 15 transactions per branch
                past_date = now - timedelta(days=random.randint(0, 30))
                
                selected_products = random.sample(product_list, random.randint(1, 4))
                total_amount = 0
                
                txn = Transaction.objects.create(
                    branch=branch,
                    user=staff,
                    subtotal_amount=0,
                    total_amount=0,
                    transaction_status='Completed'
                )
                
                for prod in selected_products:
                    qty = random.randint(1, 3)
                    subtotal = float(prod.price) * qty
                    total_amount += subtotal
                    TransactionItem.objects.create(
                        transaction=txn, product=prod, quantity=qty, unit_price=prod.price, subtotal=subtotal
                    )
                
                txn.subtotal_amount = total_amount
                txn.total_amount = total_amount
                txn.save()
                
                # Force the historical date
                Transaction.objects.filter(pk=txn.pk).update(transaction_date=past_date)
                
                PaymentRecord.objects.create(
                    transaction=txn,
                    amount_paid=total_amount,
                    payment_method=random.choice(payment_methods)
                )

        # 7. Generate Pending Restock Requests for the Queue
        padre_garcia_mgr = User.objects.get(email="manager_2@sweetbox.ph")
        RestockRequest.objects.create(
            ingredient=ingredients["Fresh Eggs"], user=padre_garcia_mgr, source_branch=main_hub,
            destination_branch=branches["Padre Garcia"], requested_quantity=20.00, status='Pending'
        )
        RestockRequest.objects.create(
            ingredient=ingredients["Coffee Beans"], user=padre_garcia_mgr, source_branch=main_hub,
            destination_branch=branches["Padre Garcia"], requested_quantity=15.00, status='Pending'
        )

        # 8. Generate Pending AI Prescriptions
        PrescriptiveOutput.objects.create(
            branch=main_hub, ingredient=ingredients["Unsalted Butter"],
            output_type='Restock Prescription',
            recommendation="Order 50.0 kg of Unsalted Butter",
            justification="(Auto-bounded to satisfy constraints) Given current trends, a 50kg order is the maximum feasible replenishment to avoid stockouts before the weekend.",
            recommended_quantity=50.00, estimated_cost=17500.00, status="Pending Review"
        )
        PrescriptiveOutput.objects.create(
            branch=branches["Padre Garcia"], ingredient=ingredients["Cream Cheese"],
            output_type='Restock Prescription',
            recommendation="Order 100.0 kg of Cream Cheese",
            justification="WARNING: AI quantity fails Supplier Minimum. Suggest manual override to combine orders with adjacent branches.",
            recommended_quantity=100.00, estimated_cost=45000.00, status="Flagged - Needs Override"
        )

        self.stdout.write(self.style.SUCCESS("Database seeded with full operational test data!"))