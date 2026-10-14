import random
from inventory.models import (
    Ingredient, BillOfMaterial, IngredientStock, ProductStock,
    RestockRequest, ConstraintParameter, StockAdjustment, ProductTransfer
)
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import Branch
from pos.models import Product, ProductCategory, Transaction, TransactionItem, PaymentRecord
from inventory.models import Ingredient, BillOfMaterial, IngredientStock, ProductStock, RestockRequest, ConstraintParameter
from analytics.models import PrescriptiveOutput
from inventory.menu_loader import MASTER_INGREDIENTS, make_recipe, parse_excel_menu

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with full RBAC accounts, official Sweet Box menu, recipes, inventory, and analytics.'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        PaymentRecord.objects.all().delete()
        TransactionItem.objects.all().delete()
        Transaction.objects.all().delete()
        StockAdjustment.objects.all().delete()
        RestockRequest.objects.all().delete()
        ProductTransfer.objects.all().delete()
        PrescriptiveOutput.objects.all().delete()
        ConstraintParameter.objects.all().delete()
        BillOfMaterial.objects.all().delete()
        ProductStock.objects.all().delete()
        IngredientStock.objects.all().delete()
        Product.objects.all().delete()
        Ingredient.objects.all().delete()
        ProductCategory.objects.all().delete()
        self.stdout.write("Starting official Sweet Box database seeding...")

        # -----------------------------------------------------------------
        # 1. Establish Branches (with duplicate deduplication)
        # -----------------------------------------------------------------
        
        branch_names = [
            'Ibaan (Main Hub)', 'Padre Garcia', 'San Jose', 
            'Sampaguita', 'South Supermarket Lipa', 'San Antonio Quezon', 'Cuenca'
        ]
        branches = {}
        for name in branch_names:
            is_hub = ('Ibaan' in name)
            branch_qs = Branch.objects.filter(name__iexact=name).order_by('branch_ID')
            if branch_qs.count() > 1:
                b = branch_qs.first()
                for dup_b in branch_qs[1:]:
                    User.objects.filter(branch=dup_b).update(branch=b)
                    IngredientStock.objects.filter(branch=dup_b).delete()
                    ProductStock.objects.filter(branch=dup_b).delete()
                    Transaction.objects.filter(branch=dup_b).update(branch=b)
                    dup_b.delete()
            elif branch_qs.exists():
                b = branch_qs.first()
            else:
                b = Branch.objects.create(name=name, main_hub=is_hub, address=f"{name}, Batangas")

            if b.main_hub != is_hub:
                b.main_hub = is_hub
                b.save()
            branches[name] = b

        main_hub = branches['Ibaan (Main Hub)']

        # -----------------------------------------------------------------
        # 2. Establish Branch-Specific RBAC Accounts
        # -----------------------------------------------------------------
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

            # Branch Manager (SCM/Inventory)
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

        # Official Sweet Box Team Accounts
        official_team = [
            {
                'name': 'Cristian Javier',
                'email': 'cristianjohua@gmail.com',
                'role': 'Business Owner',
                'branch': branches['Ibaan (Main Hub)'],
                'is_staff': True,
            },
            {
                'name': 'CJ Javier',
                'email': 'ceejay122421@gmail.com',
                'role': 'Staff',
                'branch': branches['Ibaan (Main Hub)'],
                'is_staff': False,
            },
            {
                'name': 'Brent Aclan',
                'email': 'brentaclan@gmail.com',
                'role': 'Staff',
                'branch': branches['San Jose'],
                'is_staff': False,
            },
            {
                'name': 'Aclan Brent',
                'email': 'msclick15@gmail.com',
                'role': 'Branch Manager',
                'branch': branches['San Jose'],
                'is_staff': False,
            },
            {
                'name': 'JP Claveria',
                'email': 'johnpaoloclaveria25@gmail.com',
                'role': 'Staff',
                'branch': branches['Padre Garcia'],
                'is_staff': False,
            },
            {
                'name': 'Claveria JP',
                'email': 'jpclaveria9@gmail.com',
                'role': 'Branch Manager',
                'branch': branches['Padre Garcia'],
                'is_staff': False,
            },
        ]

        for member in official_team:
            team_user, _ = User.objects.get_or_create(email=member['email'])
            team_user.set_password('Sweetbox123!')
            team_user.name = member['name']
            team_user.role = member['role']
            team_user.branch = member['branch']
            team_user.is_staff = member.get('is_staff', False)
            team_user.is_active = True
            team_user.save()

        # -----------------------------------------------------------------
        # 3. Seed Validated Commercial Master Ingredients
        # -----------------------------------------------------------------
        self.stdout.write("Seeding master ingredients...")
        ingredients = {}
        for ing_name, (unit, cost_val, cat_name) in MASTER_INGREDIENTS.items():
            cat_obj, _ = ProductCategory.objects.get_or_create(category_name=cat_name)
            cost_dec = Decimal(str(cost_val))
            ing_obj, _ = Ingredient.objects.update_or_create(
                ingredient_name=ing_name,
                defaults={
                    'category': cat_obj,
                    'measurement_unit': unit,
                    'cost_per_unit': cost_dec
                }
            )
            ingredients[ing_name] = ing_obj

        # -----------------------------------------------------------------
        # 4. Parse Excel Menu & Clean Legacy Mock Products
        # -----------------------------------------------------------------
        self.stdout.write("Parsing Excel workbooks (Sweetboox_Menu.xlsx & SweetBox_Cakes_Pastries.xlsx)...")
        all_menu_items = parse_excel_menu()
        self.stdout.write(f"Parsed {len(all_menu_items)} commercial items from Excel sheets.")

        official_names_lower = {item['name'].strip().lower() for item in all_menu_items}

        # Deduplicate & clear legacy mock products not in official menu
        legacy_products = [p for p in Product.objects.all() if p.product_name.strip().lower() not in official_names_lower]
        if legacy_products:
            self.stdout.write(f"Clearing {len(legacy_products)} legacy mock product records...")
            for lp in legacy_products:
                BillOfMaterial.objects.filter(product=lp).delete()
                ProductStock.objects.filter(product=lp).delete()
                TransactionItem.objects.filter(product=lp).delete()
                lp.delete()

        # Seed official products
        products = {}
        product_list = []
        for p_data in all_menu_items:
            cat_obj, _ = ProductCategory.objects.get_or_create(category_name=p_data['category'])
            price_dec = Decimal(str(p_data['price']))
            prod_obj, _ = Product.objects.update_or_create(
                product_name=p_data['name'],
                defaults={
                    'category': cat_obj,
                    'price': price_dec,
                    'is_active': True
                }
            )
            products[p_data['name']] = prod_obj
            product_list.append(prod_obj)

        # -----------------------------------------------------------------
        # 5. Seed Commercial Bill of Materials (BOM) Recipes
        # -----------------------------------------------------------------
        self.stdout.write("Generating commercial BOM recipes with 31%-37% COGS target...")
        bom_count = 0
        for p_data in all_menu_items:
            prod_obj = products[p_data['name']]
            recipe = make_recipe(p_data['name'], p_data['category'], p_data['size_tag'])
            for ing_name, req_qty, req_unit in recipe:
                ing_obj = ingredients.get(ing_name)
                if ing_obj:
                    BillOfMaterial.objects.update_or_create(
                        product=prod_obj,
                        ingredient=ing_obj,
                        defaults={
                            'quantity_required': Decimal(str(req_qty)),
                            'measurement_unit': req_unit
                        }
                    )
                    bom_count += 1

        self.stdout.write(f"Seeded {bom_count} Bill of Material deductions across {len(products)} products.")

        # -----------------------------------------------------------------
        # 6. Distribute Initial Stock & Constraints Across All 7 Branches
        # -----------------------------------------------------------------
        self.stdout.write("Seeding branch inventory and constraint parameters...")
        now = timezone.now()

        for branch_name, branch in branches.items():
            is_hub = branch.main_hub

            # Ingredient Stocks & Constraints
            for ing_name, ing_obj in ingredients.items():
                if is_hub:
                    qty = Decimal(str(random.choice([50, 75, 100, 150])))
                else:
                    qty = Decimal(str(random.choice([15, 25, 40, 60])))

                days_to_expiry = random.choice([30, 60, 90, 180, None])
                expiry = (now + timedelta(days=days_to_expiry)) if days_to_expiry else None

                IngredientStock.objects.update_or_create(
                    branch=branch,
                    ingredient=ing_obj,
                    defaults={
                        'quantity_available': qty,
                        'reorder_threshold': Decimal('10.00'),
                        'total_cost': round(qty * ing_obj.cost_per_unit, 2),
                        'expiry_date': expiry,
                        'batch_number': f"BATCH-{branch.pk}-{random.randint(100, 999)}"
                    }
                )

                ConstraintParameter.objects.update_or_create(
                    branch=branch,
                    ingredient=ing_obj,
                    defaults={
                        'lead_time_days': 2,
                        'min_order_quantity': Decimal('5.00'),
                        'max_order_quantity': Decimal('100.00'),
                        'production_limit': Decimal('50.00'),
                        'capacity_limit': Decimal('200.00')
                    }
                )

            # Product Stocks
            for prod_name, prod_obj in products.items():
                if is_hub:
                    p_qty = Decimal(str(random.choice([5, 10, 15, 20])))
                else:
                    p_qty = Decimal(str(random.choice([2, 4, 8, 12])))

                ProductStock.objects.update_or_create(
                    branch=branch,
                    product=prod_obj,
                    defaults={
                        'quantity_available': p_qty,
                        'reorder_threshold': Decimal('5.00'),
                        'total_cost': Decimal('0.00')
                    }
                )

        # -----------------------------------------------------------------
        # 7. Generate Mock POS Transactions for Live Analytics & Charts
        # -----------------------------------------------------------------
        self.stdout.write("Generating POS transactions for branch analytics...")
        payment_methods = ['Cash', 'GCash', 'Maya', 'Split Payment']
        for branch in branches.values():
            staff = User.objects.filter(branch=branch, role='Staff').first()
            if not staff:
                continue
            for _ in range(15):
                past_date = now - timedelta(days=random.randint(0, 30))
                selected_products = random.sample(product_list, random.randint(1, 4))
                total_amount = Decimal('0.00')

                txn = Transaction.objects.create(
                    branch=branch,
                    user=staff,
                    subtotal_amount=Decimal('0.00'),
                    total_amount=Decimal('0.00'),
                    transaction_status='Completed'
                )

                for prod in selected_products:
                    qty = random.randint(1, 3)
                    subtotal = prod.price * qty
                    total_amount += subtotal
                    TransactionItem.objects.create(
                        transaction=txn,
                        product=prod,
                        quantity=qty,
                        unit_price=prod.price,
                        subtotal=subtotal
                    )

                txn.subtotal_amount = total_amount
                txn.total_amount = total_amount
                txn.save()

                Transaction.objects.filter(pk=txn.pk).update(transaction_date=past_date)

                PaymentRecord.objects.create(
                    transaction=txn,
                    amount_paid=total_amount,
                    payment_method=random.choice(payment_methods)
                )

        # -----------------------------------------------------------------
        # 8. Generate Pending Restock Queue & AI Prescriptions
        # -----------------------------------------------------------------
        padre_garcia_mgr = User.objects.filter(email="manager_2@sweetbox.ph").first()
        if padre_garcia_mgr:
            RestockRequest.objects.get_or_create(
                ingredient=ingredients["Fresh Eggs"],
                destination_branch=branches["Padre Garcia"],
                status='Pending',
                defaults={
                    'user': padre_garcia_mgr,
                    'source_branch': main_hub,
                    'requested_quantity': Decimal('20.00')
                }
            )
            RestockRequest.objects.get_or_create(
                ingredient=ingredients["Espresso Coffee Beans"],
                destination_branch=branches["Padre Garcia"],
                status='Pending',
                defaults={
                    'user': padre_garcia_mgr,
                    'source_branch': main_hub,
                    'requested_quantity': Decimal('15.00')
                }
            )

        PrescriptiveOutput.objects.get_or_create(
            branch=main_hub,
            ingredient=ingredients["Unsalted Butter"],
            output_type='Restock Prescription',
            recommendation="Order 50.0 kg of Unsalted Butter",
            defaults={
                "justification": "(Auto-bounded to satisfy constraints) Given current trends, a 50kg order is the maximum feasible replenishment to avoid stockouts before the weekend.",
                "recommended_quantity": Decimal('50.00'),
                "estimated_cost": Decimal('18000.00'),
                "status": "Pending Review"
            }
        )

        PrescriptiveOutput.objects.get_or_create(
            branch=branches["Padre Garcia"],
            ingredient=ingredients["Cream Cheese"],
            output_type='Restock Prescription',
            recommendation="Order 100.0 kg of Cream Cheese",
            defaults={
                "justification": "WARNING: AI quantity fails Supplier Minimum. Suggest manual override to combine orders with adjacent branches.",
                "recommended_quantity": Decimal('100.00'),
                "estimated_cost": Decimal('45000.00'),
                "status": "Flagged - Needs Override"
            }
        )

        self.stdout.write(self.style.SUCCESS("Database seeded successfully with official Sweet Box commercial menu!"))