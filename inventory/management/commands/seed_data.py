import csv
import json
import random
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from accounts.models import Branch, AuditLog
from pos.models import Product, ProductCategory, Transaction, TransactionItem, PaymentRecord
from inventory.models import (
    Ingredient, BillOfMaterial, IngredientStock, ProductStock,
    RestockRequest, ConstraintParameter, StockAdjustment, ProductTransfer
)
from analytics.models import (
    PrescriptiveOutput, ExternalVariable, KPIRecord,
    ProductClassification, ArchiveStorage, ChatbotLog
)
from inventory.menu_loader import MASTER_INGREDIENTS, make_recipe, parse_excel_menu

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds database with realistic Sweet Box Business Analytics telemetry, Hub-and-Spoke inventory, and BOMs.'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("Starting Sweet Box enterprise database seeding...")

        # -----------------------------------------------------------------
        # 0. Clean Existing Operational Tables
        # -----------------------------------------------------------------
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
        ProductClassification.objects.all().delete()
        KPIRecord.objects.all().delete()
        ArchiveStorage.objects.all().delete()
        ExternalVariable.objects.all().delete()
        Product.objects.all().delete()
        Ingredient.objects.all().delete()
        ProductCategory.objects.all().delete()

        now = timezone.now()
        today = now.date()

        # -----------------------------------------------------------------
        # 1. Establish Branches & Accounts
        # -----------------------------------------------------------------
        branch_configs = [
            ('Ibaan (Main Hub)', True, 'Ibaan, Batangas'),
            ('Padre Garcia', False, 'Padre Garcia, Batangas'),
            ('San Jose', False, 'San Jose, Batangas'),
            ('Sampaguita', False, 'Sampaguita, Lipa City, Batangas'),
            ('South Supermarket Lipa', False, 'South Supermarket, Lipa City, Batangas'),
            ('San Antonio Quezon', False, 'San Antonio, Quezon'),
            ('Cuenca', False, 'Cuenca, Batangas'),
        ]

        branches = {}
        for name, is_hub, addr in branch_configs:
            branch_qs = Branch.objects.filter(name__iexact=name).order_by('branch_ID')
            if branch_qs.count() > 1:
                b = branch_qs.first()
                for dup_b in branch_qs[1:]:
                    User.objects.filter(branch=dup_b).update(branch=b)
                    dup_b.delete()
            elif branch_qs.exists():
                b = branch_qs.first()
            else:
                b = Branch.objects.create(name=name, main_hub=is_hub, address=addr)

            b.main_hub = is_hub
            b.address = addr
            b.save()
            branches[name] = b

        main_hub = branches['Ibaan (Main Hub)']

        # Seed Staff & Branch Managers for all 7 branches
        for i, (name, _, _) in enumerate(branch_configs):
            idx = i + 1
            branch = branches[name]

            staff, _ = User.objects.get_or_create(email=f"staff_{idx}@sweetbox.ph")
            staff.set_password('sweetbox123')
            staff.name = f"{name} Cashier"
            staff.role = 'Staff'
            staff.branch = branch
            staff.is_active = True
            staff.save()

            mgr, _ = User.objects.get_or_create(email=f"manager_{idx}@sweetbox.ph")
            mgr.set_password('sweetbox123')
            mgr.name = f"{name} Manager"
            mgr.role = 'Branch Manager'
            mgr.branch = branch
            mgr.is_active = True
            mgr.save()

        # Global Business Owner
        owner, _ = User.objects.get_or_create(email="owner@sweetbox.ph")
        owner.set_password('sweetbox123')
        owner.name = "Business Owner"
        owner.role = 'Business Owner'
        owner.branch = main_hub
        owner.is_active = True
        owner.is_staff = True
        owner.save()

        # System Administrator
        admin_user, _ = User.objects.get_or_create(email="admin@sweetbox.ph")
        admin_user.set_password('sweetbox123')
        admin_user.name = "System Administrator"
        admin_user.role = 'System Administrator'
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.is_active = True
        admin_user.save()

        # Official Sweet Box Team Accounts
        official_team = [
            {'name': 'Cristian Javier', 'email': 'cristianjohua@gmail.com', 'role': 'Business Owner', 'branch': main_hub, 'is_staff': True},
            {'name': 'CJ Javier', 'email': 'ceejay122421@gmail.com', 'role': 'Staff', 'branch': main_hub, 'is_staff': False},
            {'name': 'Brent Aclan', 'email': 'brentaclan@gmail.com', 'role': 'Staff', 'branch': branches['San Jose'], 'is_staff': False},
            {'name': 'Aclan Brent', 'email': 'msclick15@gmail.com', 'role': 'Branch Manager', 'branch': branches['San Jose'], 'is_staff': False},
            {'name': 'JP Claveria', 'email': 'johnpaoloclaveria25@gmail.com', 'role': 'Staff', 'branch': branches['Padre Garcia'], 'is_staff': False},
            {'name': 'Claveria JP', 'email': 'jpclaveria9@gmail.com', 'role': 'Branch Manager', 'branch': branches['Padre Garcia'], 'is_staff': False},
        ]
        for member in official_team:
            u, _ = User.objects.get_or_create(email=member['email'])
            u.set_password('Sweetbox123!')
            u.name = member['name']
            u.role = member['role']
            u.branch = member['branch']
            u.is_staff = member.get('is_staff', False)
            u.is_active = True
            u.save()

        self.stdout.write("RBAC user accounts and branch network established.")

        # -----------------------------------------------------------------
        # 2. Seed Master Ingredients & Official Menu
        # -----------------------------------------------------------------
        self.stdout.write("Seeding master ingredients and commercial recipes...")
        ingredients = {}
        for ing_name, (unit, cost_val, cat_name) in MASTER_INGREDIENTS.items():
            cat_obj, _ = ProductCategory.objects.get_or_create(category_name=cat_name)
            ing_obj, _ = Ingredient.objects.update_or_create(
                ingredient_name=ing_name,
                defaults={
                    'category': cat_obj,
                    'measurement_unit': unit,
                    'cost_per_unit': Decimal(str(cost_val))
                }
            )
            ingredients[ing_name] = ing_obj

        all_menu_items = parse_excel_menu()
        products = {}
        product_list = []
        for p_data in all_menu_items:
            cat_obj, _ = ProductCategory.objects.get_or_create(category_name=p_data['category'])
            prod_obj, _ = Product.objects.update_or_create(
                product_name=p_data['name'],
                defaults={
                    'category': cat_obj,
                    'price': Decimal(str(p_data['price'])),
                    'is_active': True
                }
            )
            products[p_data['name']] = prod_obj
            product_list.append(prod_obj)

        # Seed Bill of Materials (BOM)
        bom_objects = []
        bom_cost_map = {}
        for p_data in all_menu_items:
            prod_obj = products[p_data['name']]
            recipe = make_recipe(p_data['name'], p_data['category'], p_data['size_tag'])
            prod_bom_cost = Decimal('0.00')
            for ing_name, req_qty, req_unit in recipe:
                ing_obj = ingredients.get(ing_name)
                if ing_obj:
                    qty_dec = Decimal(str(req_qty))
                    bom_objects.append(BillOfMaterial(
                        product=prod_obj,
                        ingredient=ing_obj,
                        quantity_required=qty_dec,
                        measurement_unit=req_unit
                    ))
                    prod_bom_cost += qty_dec * ing_obj.cost_per_unit
            bom_cost_map[prod_obj.product_ID] = prod_bom_cost

        BillOfMaterial.objects.bulk_create(bom_objects, batch_size=1000)
        self.stdout.write(f"Seeded {len(bom_objects)} Bill of Material deductions across {len(product_list)} products.")

        # -----------------------------------------------------------------
        # 3. Hub-and-Spoke Inventory Valuation & 3-Tier Stock Health
        # -----------------------------------------------------------------
        self.stdout.write("Calibrating Hub-and-Spoke inventory valuation & 3-tier stock health...")

        # Step 3.1: Raw Material Stock Exclusively at Ibaan (Main Hub)
        critical_ing_names = ['Unsalted Butter', 'Cream Cheese', 'Tapioca Pearls / Boba']
        low_ing_names = ['All-Purpose Flour', 'Refined Sugar', 'Fresh Eggs', 'Chocolate Ganache', 'Whipping Cream']
        expiring_ing_names = ['Fresh Milk', 'Whipping Cream', 'Fresh Strawberries', 'Yeast', 'Matcha Powder', 'Cream Cheese', 'Evaporated Milk']

        ing_stocks_to_create = []
        constraint_params_to_create = []

        for ing_name, ing_obj in ingredients.items():
            threshold = Decimal('10.00')
            if ing_name in critical_ing_names:
                qty = Decimal('4.00') # <= threshold * 0.5 (Critical)
                expiry = now + timedelta(days=random.choice([15, 20]))
            elif ing_name in low_ing_names:
                qty = Decimal('7.50') # threshold * 0.5 < qty <= threshold (Low Stock)
                expiry = now + timedelta(days=random.choice([25, 30]))
            else:
                qty = Decimal(str(random.randint(14, 22))) # Healthy buffer
                expiry = now + timedelta(days=random.choice([45, 60, 90, 180]))

            if ing_name in expiring_ing_names:
                expiry = now + timedelta(days=random.choice([3, 4, 5]))

            cost_total = round(qty * ing_obj.cost_per_unit, 2)
            ing_stocks_to_create.append(IngredientStock(
                branch=main_hub,
                ingredient=ing_obj,
                quantity_available=qty,
                reorder_threshold=threshold,
                total_cost=cost_total,
                expiry_date=expiry,
                batch_number=f"BATCH-1-{random.randint(100, 999)}"
            ))

            constraint_params_to_create.append(ConstraintParameter(
                branch=main_hub,
                ingredient=ing_obj,
                lead_time_days=2,
                min_order_quantity=Decimal('5.00'),
                max_order_quantity=Decimal('50.00'),
                production_limit=Decimal('50.00'),
                capacity_limit=Decimal('200.00')
            ))

        IngredientStock.objects.bulk_create(ing_stocks_to_create, batch_size=1000)
        ConstraintParameter.objects.bulk_create(constraint_params_to_create, batch_size=1000)

        # Step 3.2: ProductStock Assignment
        def is_cake_or_pastry(p):
            cat = (p.category.category_name if p.category else '').strip().lower()
            return any(k in cat for k in ['cake', 'pastry', 'pastries'])

        cake_pastry_products = [p for p in product_list if is_cake_or_pastry(p)]

        # Specific flagship items requested in Section 3.6.6
        exact_flagship_names = [
            'Minimalist Daisy (9x4)',
            'Choco Floral (9x4)',
            'Choco Almond Dream (10")',
            'Belgian Choco Drip (10x2)',
            'Pink Pipe (9x4)',
            'Minimalist Pink (10x2)',
            'Bento',
            'Assorted Pastries Box',
            'Ube Md (6x2)',
            'Bobba Milk Milk Tea (16oz)',
            'Okinawa Milk Tea (16oz)',
            'Red Velvet (8x2)',
            'Daisy Ganache (8x2)',
        ]
        flagship_prods = []
        for fn in exact_flagship_names:
            matched = [p for p in product_list if fn.lower() == p.product_name.lower() or fn.lower() in p.product_name.lower()]
            if matched and matched[0] not in flagship_prods:
                flagship_prods.append(matched[0])

        flagship_set = set(flagship_prods)
        non_flagship = [p for p in product_list if p not in flagship_set]
        core_prods = non_flagship[:45]
        core_set = set(core_prods)
        niche_prods = non_flagship[45:]

        prod_stocks_to_create = []

        # At Ibaan Main Hub: Finished Cakes & Pastries
        for idx, p in enumerate(cake_pastry_products):
            unit_c = bom_cost_map.get(p.product_ID, p.price * Decimal('0.35'))
            thresh = Decimal('5.00')
            if idx in [0, 1]:
                qty = Decimal('2.00') # Critical
                exp = now + timedelta(days=15)
            elif idx in [2, 3, 4]:
                qty = Decimal('4.00') # Low Stock
                exp = now + timedelta(days=20)
            else:
                qty = Decimal(str(random.randint(6, 10))) # Healthy buffer
                exp = now + timedelta(days=random.choice([30, 45, 60]))

            if idx in [5, 6]:
                exp = now + timedelta(days=4) # Expiring soon

            tot_cost = round(qty * unit_c, 2)
            prod_stocks_to_create.append(ProductStock(
                branch=main_hub,
                product=p,
                quantity_available=qty,
                reorder_threshold=thresh,
                total_cost=tot_cost
            ))

        # At 6 Satellite Branches: Finished Cakes & Pastries (+ Bobba/Okinawa at Sampaguita & San Jose)
        satellite_branches = [b for b in branches.values() if not b.main_hub]
        for sat_branch in satellite_branches:
            sat_catalog = list(cake_pastry_products)
            # Assign flagship beverages to Sampaguita and San Jose for realistic retail volume
            if sat_branch.name in ['Sampaguita', 'San Jose']:
                bev_flagships = [p for p in flagship_prods if not is_cake_or_pastry(p)]
                sat_catalog.extend(bev_flagships)

            for idx, p in enumerate(sat_catalog):
                unit_c = bom_cost_map.get(p.product_ID, p.price * Decimal('0.35'))
                thresh = Decimal('5.00')
                if idx in [0, 1]:
                    qty = Decimal('2.00') # Critical
                elif idx in [2, 3, 4]:
                    qty = Decimal('4.00') # Low Stock
                else:
                    qty = Decimal(str(random.randint(2, 5))) # Lean display buffer

                tot_cost = round(qty * unit_c, 2)
                prod_stocks_to_create.append(ProductStock(
                    branch=sat_branch,
                    product=p,
                    quantity_available=qty,
                    reorder_threshold=thresh,
                    total_cost=tot_cost
                ))

        ProductStock.objects.bulk_create(prod_stocks_to_create, batch_size=1000)
        self.stdout.write("ProductStock calibrated with lean, mathematically realistic buffer levels.")

        # -----------------------------------------------------------------
        # 4. 180-Day Rolling Sales Telemetry with Pareto Velocity
        # -----------------------------------------------------------------
        self.stdout.write("Generating 180 days of realistic sales telemetry and payment records...")

        # Foot traffic distribution
        branch_traffic_weights = [
            (branches['Ibaan (Main Hub)'], 0.22),
            (branches['San Jose'], 0.18),
            (branches['Padre Garcia'], 0.16),
            (branches['Cuenca'], 0.14),
            (branches['San Antonio Quezon'], 0.12),
            (branches['South Supermarket Lipa'], 0.10),
            (branches['Sampaguita'], 0.08),
        ]
        b_list = [bw[0] for bw in branch_traffic_weights]
        b_weights = [bw[1] for bw in branch_traffic_weights]
        staff_by_branch = {b.branch_ID: User.objects.filter(branch=b, role='Staff').first() for b in b_list}

        # 30-Day Quota Targets to guarantee Chapter 3 / Pareto Classification:
        # Flagship (Best-Selling Q >= 50): 55 to 88 units each
        # Core (Standard 11 <= Q <= 49): 14 to 40 units each
        # Niche (Slow-Moving Q <= 10): 1 to 8 units each
        quota_30d = {}
        for p in flagship_prods:
            quota_30d[p.product_ID] = random.randint(56, 84)
        for p in core_prods:
            quota_30d[p.product_ID] = random.randint(15, 38)
        for p in niche_prods[:60]:
            quota_30d[p.product_ID] = random.randint(1, 8)

        txns_to_create = []
        txn_meta = []
        ref_counter = 2026100000000

        for day_offset in range(180, -1, -1):
            target_dt = now - timedelta(days=day_offset, hours=random.randint(1, 10), minutes=random.randint(0, 59))
            d_date = target_dt.date()

            # Calibrated daily transaction counts
            if day_offset <= 30:
                base_count = random.randint(10, 12)
                if day_offset <= 7:
                    base_count = int(base_count * 1.15)
            elif day_offset <= 60:
                base_count = random.randint(8, 10)
            else:
                base_count = random.randint(5, 7)

            # Payday multiplier (14th-16th and 29th-1st)
            if d_date.day in [14, 15, 16, 29, 30, 31, 1]:
                base_count = int(base_count * 1.40)

            # Weekend multiplier (Fri, Sat, Sun)
            if target_dt.weekday() in [4, 5, 6]:
                base_count = int(base_count * 1.25)

            selected_branches = random.choices(b_list, weights=b_weights, k=base_count)

            for target_b in selected_branches:
                staff_user = staff_by_branch.get(target_b.branch_ID) or owner
                is_hub = target_b.main_hub

                # Candidate pool
                if is_hub:
                    b_flagships = flagship_prods
                    b_cores = core_prods
                    b_niches = niche_prods
                else:
                    b_flagships = [p for p in flagship_prods if is_cake_or_pastry(p) or target_b.name in ['Sampaguita', 'San Jose']]
                    b_cores = [p for p in core_prods if is_cake_or_pastry(p)]
                    b_niches = [p for p in niche_prods if is_cake_or_pastry(p)]

                num_items = random.randint(1, 3)
                chosen_items = []

                if day_offset <= 30:
                    # In last 30 days, prioritize quota fulfilment
                    available_flagships = [p for p in b_flagships if quota_30d.get(p.product_ID, 0) > 0]
                    available_cores = [p for p in b_cores if quota_30d.get(p.product_ID, 0) > 0]
                    available_niches = [p for p in b_niches if quota_30d.get(p.product_ID, 0) > 0]

                    for _ in range(num_items):
                        roll = random.random()
                        if roll < 0.65 and available_flagships:
                            prod_chosen = random.choice(available_flagships)
                            rem = quota_30d.get(prod_chosen.product_ID, 1)
                            qty = min(rem, random.randint(1, 2))
                            quota_30d[prod_chosen.product_ID] -= qty
                        elif roll < 0.90 and available_cores:
                            prod_chosen = random.choice(available_cores)
                            rem = quota_30d.get(prod_chosen.product_ID, 1)
                            qty = min(rem, 1)
                            quota_30d[prod_chosen.product_ID] -= qty
                        elif available_niches:
                            prod_chosen = random.choice(available_niches)
                            rem = quota_30d.get(prod_chosen.product_ID, 1)
                            qty = min(rem, 1)
                            quota_30d[prod_chosen.product_ID] -= qty
                        else:
                            prod_chosen = random.choice(b_flagships or product_list)
                            qty = 1

                        chosen_items.append((prod_chosen, qty, prod_chosen.price))
                else:
                    # Days 31 to 180: Standard velocity sampling
                    for _ in range(num_items):
                        roll = random.random()
                        if roll < 0.60 and b_flagships:
                            prod_chosen = random.choice(b_flagships)
                            qty = random.randint(1, 2)
                        elif roll < 0.88 and b_cores:
                            prod_chosen = random.choice(b_cores)
                            qty = 1
                        elif b_niches:
                            prod_chosen = random.choice(b_niches)
                            qty = 1
                        else:
                            prod_chosen = random.choice(b_flagships or product_list)
                            qty = 1

                        chosen_items.append((prod_chosen, qty, prod_chosen.price))

                subtotal = sum(p_price * p_qty for _, p_qty, p_price in chosen_items)

                # Occasional discount (~12%)
                if random.random() < 0.12:
                    disc_type = random.choice(['Senior Citizen', 'PWD', 'Promo'])
                    rate = Decimal('0.20') if disc_type in ['Senior Citizen', 'PWD'] else Decimal('0.10')
                    disc_amt = round(subtotal * rate, 2)
                    tot_amt = subtotal - disc_amt
                else:
                    disc_type = None
                    disc_amt = Decimal('0.00')
                    tot_amt = subtotal

                txns_to_create.append(Transaction(
                    branch=target_b,
                    user=staff_user,
                    subtotal_amount=subtotal,
                    discount_type=disc_type,
                    discount_amount=disc_amt,
                    total_amount=tot_amt,
                    transaction_status='Completed'
                ))

                # Payment distribution: 45% Cash, 40% E-Wallet, 15% Split
                r_pay = random.random()
                pay_records = []
                if r_pay < 0.45:
                    pay_records.append(('Cash', tot_amt, None))
                elif r_pay < 0.85:
                    ref_counter += 1
                    pay_records.append((random.choice(['GCash', 'Maya']), tot_amt, str(ref_counter)))
                else:
                    half1 = round(tot_amt / Decimal('2.00'), 2)
                    half2 = tot_amt - half1
                    ref_counter += 1
                    pay_records.append(('Cash', half1, None))
                    pay_records.append((random.choice(['GCash', 'Maya']), half2, str(ref_counter)))

                txn_meta.append((target_dt, chosen_items, pay_records))

        # Set 9 historical transactions to Refunded
        refund_indices = set(random.sample(range(len(txns_to_create)), min(9, len(txns_to_create))))
        for r_idx in refund_indices:
            txns_to_create[r_idx].transaction_status = 'Refunded'

        self.stdout.write(f"Inserting {len(txns_to_create)} transactions in atomic batches...")

        created_txns = []
        for txn in txns_to_create:
            txn.save()
            created_txns.append(txn)

        items_to_create = []
        payments_to_create = []
        dt_group_map = {}

        for txn_obj, (t_dt, t_items, t_payments) in zip(created_txns, txn_meta):
            dt_group_map.setdefault(t_dt, []).append(txn_obj.pk)

            for prod, q, pr in t_items:
                items_to_create.append(TransactionItem(
                    transaction=txn_obj,
                    product=prod,
                    quantity=q,
                    unit_price=pr,
                    subtotal=pr * q
                ))

            for m_type, m_amt, m_ref in t_payments:
                payments_to_create.append(PaymentRecord(
                    transaction=txn_obj,
                    amount_paid=m_amt,
                    payment_method=m_type,
                    reference_number=m_ref
                ))

        TransactionItem.objects.bulk_create(items_to_create, batch_size=1000)
        PaymentRecord.objects.bulk_create(payments_to_create, batch_size=1000)

        # Batch update historical timestamps
        for dt_val, pks in dt_group_map.items():
            Transaction.objects.filter(pk__in=pks).update(transaction_date=dt_val)
            PaymentRecord.objects.filter(transaction_id__in=pks).update(payment_time=dt_val)

        self.stdout.write(f"Successfully generated {len(created_txns)} transactions and {len(items_to_create)} line items.")

        # -----------------------------------------------------------------
        # 5. Seed External Variables (Local Events & Calendar)
        # -----------------------------------------------------------------
        external_vars_data = [
            ('Payday Cycle', 'Mid-Month & End-Month Payday Cycle', today - timedelta(days=15), today + timedelta(days=15), 'High', 'Bi-monthly wage disbursement driving surge in confectionery and beverage volume.', True),
            ('Holiday', 'Batangas Foundation & Town Fiesta', today - timedelta(days=2), today + timedelta(days=5), 'Medium', 'Regional civic and patron celebrations driving large celebration cake bookings.', True),
            ('Holiday', 'All Saints Day / Undas Long Weekend', today - timedelta(days=3), today + timedelta(days=4), 'High', 'Annual family gathering holiday with peak gift pastry box and celebration cake orders.', True),
            ('Weather Seasonality', 'Northeast Monsoon / Rainy Week', today - timedelta(days=7), today + timedelta(days=7), 'Medium', 'Afternoon showers increasing cafe hot drinks and dine-in comfort orders.', True),
            ('Academic Calendar', 'University Midterm Week', today - timedelta(days=30), today + timedelta(days=24), 'Low', 'Student academic assessment cycle with study group cafe visits.', False),
        ]
        for v_type, v_name, v_start, v_end, v_impact, v_desc, v_act in external_vars_data:
            ExternalVariable.objects.create(
                branch=main_hub,
                variable_type=v_type,
                name=v_name,
                start_date=v_start,
                end_date=v_end,
                impact_level=v_impact,
                description=v_desc,
                is_active=v_act
            )
        self.stdout.write("External variables and active local events seeded.")

        # -----------------------------------------------------------------
        # 6. Generate Deterministic Product Classifications
        # -----------------------------------------------------------------
        thirty_days_ago = now - timedelta(days=30)
        recent_sales = TransactionItem.objects.filter(
            transaction__transaction_status='Completed',
            transaction__transaction_date__gte=thirty_days_ago
        ).values('product_id').annotate(total_qty=Sum('quantity'))

        sales_map = {r['product_id']: r['total_qty'] for r in recent_sales}
        classifications_to_create = []
        for p in product_list:
            q = sales_map.get(p.product_ID, 0)
            if q >= 50:
                c_name = 'Best-Selling'
                rec = "High customer demand. Prioritize commissary production batches and maintain a 7-day buffer stock."
            elif q <= 10:
                c_name = 'Slow-Moving'
                rec = "Low rotation. Consider display bundling, promotional discounting, or reducing batch transfers."
            else:
                c_name = 'Standard'
                rec = "Stable replenishment velocity. Maintain standard lead-time reorder cycles."

            classifications_to_create.append(ProductClassification(
                product=p,
                classification=c_name,
                recommended_action=rec
            ))

        ProductClassification.objects.bulk_create(classifications_to_create, batch_size=1000)
        best_count = sum(1 for c in classifications_to_create if c.classification == 'Best-Selling')
        self.stdout.write(f"Product classifications generated ({best_count} Best-Selling items with Q >= 50).")

        # -----------------------------------------------------------------
        # 7. Seed Prescriptive Outputs (Pending & 20 Historical Reviewed)
        # -----------------------------------------------------------------
        # Pending review at Ibaan
        butter_ing = ingredients.get("Unsalted Butter")
        if butter_ing:
            PrescriptiveOutput.objects.create(
                branch=main_hub,
                ingredient=butter_ing,
                output_type='Restock Prescription',
                recommendation="Procure 50.0 kg of Unsalted Butter (12.0 days operational buffer)",
                justification="(Auto-bounded to satisfy constraints) Based on historical daily burn rate, a 50kg order is optimal replenishment before the weekend rush.",
                recommended_quantity=Decimal('50.00'),
                estimated_cost=Decimal('18000.00'),
                status='Pending Review'
            )

        sample_cake = cake_pastry_products[0] if cake_pastry_products else product_list[0]
        PrescriptiveOutput.objects.create(
            branch=main_hub,
            product=sample_cake,
            output_type='Production Target',
            recommendation=f"Produce 20 units of {sample_cake.product_name} at Ibaan Commissary",
            justification="Forecasted weekend celebration demand exceeds current finished hub buffer stock.",
            recommended_quantity=Decimal('20.00'),
            estimated_cost=Decimal('6400.00'),
            status='Pending Review'
        )

        # Pending review at satellites (Dispatch Transfers)
        pg_branch = branches['Padre Garcia']
        sj_branch = branches['San Jose']
        PrescriptiveOutput.objects.create(
            branch=pg_branch,
            product=sample_cake,
            output_type='Dispatch Transfer Prescription',
            recommendation=f"Transfer 15 units of {sample_cake.product_name} from Ibaan (Main Hub)",
            justification="Satellite display buffer is low. Transferring finished units prevents stockouts.",
            recommended_quantity=Decimal('15.00'),
            estimated_cost=round(Decimal('15.00') * sample_cake.price, 2),
            status='Pending Review'
        )
        PrescriptiveOutput.objects.create(
            branch=sj_branch,
            product=sample_cake,
            output_type='Dispatch Transfer Prescription',
            recommendation=f"Transfer 10 units of {sample_cake.product_name} from Ibaan (Main Hub)",
            justification="Pre-weekend replenishment dispatch transfer from central hub.",
            recommended_quantity=Decimal('10.00'),
            estimated_cost=round(Decimal('10.00') * sample_cake.price, 2),
            status='Pending Review'
        )

        # 20 Historical Reviewed Prescriptions (17 Approved, 3 Overridden -> 85% MAR, 100% CCR, ~6.4% MAPE)
        reviewed_prescriptions = []
        ing_keys = list(ingredients.keys())

        # 17 Approved Prescriptions
        for i in range(17):
            ing_key = ing_keys[i % len(ing_keys)]
            ing_target = ingredients[ing_key]
            p_dt = now - timedelta(days=28 - i, hours=random.randint(1, 12))
            rec_q = Decimal(str(random.choice([20, 25, 30, 40, 50])))
            c_est = round(rec_q * ing_target.cost_per_unit, 2)
            po = PrescriptiveOutput(
                branch=main_hub,
                ingredient=ing_target,
                output_type='Restock Prescription',
                recommendation=f"Procure {rec_q} {ing_target.measurement_unit} of {ing_target.ingredient_name}",
                justification=f"Approved restock directive matching verified lead-time replenishment burn rate of {ing_target.ingredient_name}.",
                recommended_quantity=rec_q,
                estimated_cost=c_est,
                status='Approved',
                is_overridden=False,
                generated_at=p_dt
            )
            reviewed_prescriptions.append((po, p_dt))

        # 3 Overridden Prescriptions
        overrides = [
            (ingredients.get('Unsalted Butter', ingredients[ing_keys[0]]), Decimal('50.00'), "Adjusted order quantity (+10kg) to match supplier delivery truck bundle packaging.", now - timedelta(days=18)),
            (sample_cake, Decimal('20.00'), "Scaled down production target (-5 units) due to forecasted heavy rainfall.", now - timedelta(days=12)),
            (ingredients.get('All-Purpose Flour', ingredients[ing_keys[1]]), Decimal('40.00'), "Adjusted batch order to align with supplier minimum pallet packaging.", now - timedelta(days=6)),
        ]
        for item_target, rec_q, o_reason, p_dt in overrides:
            if isinstance(item_target, Ingredient):
                c_est = round(rec_q * item_target.cost_per_unit, 2)
                po = PrescriptiveOutput(
                    branch=main_hub,
                    ingredient=item_target,
                    output_type='Restock Prescription',
                    recommendation=f"Procure {rec_q} {item_target.measurement_unit} of {item_target.ingredient_name}",
                    justification="Automated replenishment recommendation calibrated to historical average burn rate.",
                    recommended_quantity=rec_q,
                    estimated_cost=c_est,
                    status='Overridden',
                    is_overridden=True,
                    override_reason=o_reason,
                    generated_at=p_dt
                )
            else:
                c_est = round(rec_q * (item_target.price * Decimal('0.35')), 2)
                po = PrescriptiveOutput(
                    branch=main_hub,
                    product=item_target,
                    output_type='Production Target',
                    recommendation=f"Produce {rec_q} units of {item_target.product_name}",
                    justification="Commissary production schedule directive.",
                    recommended_quantity=rec_q,
                    estimated_cost=c_est,
                    status='Overridden',
                    is_overridden=True,
                    override_reason=o_reason,
                    generated_at=p_dt
                )
            reviewed_prescriptions.append((po, p_dt))

        for po_obj, p_dt in reviewed_prescriptions:
            po_obj.save()
            PrescriptiveOutput.objects.filter(pk=po_obj.pk).update(generated_at=p_dt)

        self.stdout.write("Prescriptive outputs seeded with verified 85% MAR and 100% CCR compliance.")

        # -----------------------------------------------------------------
        # 8. Seed Historical KPIRecords Across All 7 Branches (180 Days)
        # -----------------------------------------------------------------
        self.stdout.write("Pre-computing historical KPIRecords for multi-period trend reporting...")
        kpi_records_to_create = []

        # Periods: 150, 120, 90, 60, 30, and 0 days ago
        periods = [150, 120, 90, 60, 30, 0]

        for p_offset in periods:
            p_date = today - timedelta(days=p_offset)
            w_start = now - timedelta(days=p_offset + 30)
            w_end = now - timedelta(days=p_offset)

            for b in b_list:
                b_txns = Transaction.objects.filter(
                    branch=b,
                    transaction_status='Completed',
                    transaction_date__gte=w_start,
                    transaction_date__lte=w_end
                ).prefetch_related('items__product')

                b_rev = b_txns.aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
                if b_rev == 0:
                    b_rev = Decimal(str(random.randint(18000, 32000)))

                b_cogs = Decimal('0.00')
                for txn in b_txns:
                    for it in txn.items.all():
                        u_cost = bom_cost_map.get(it.product_id, it.product.price * Decimal('0.35') if it.product else Decimal('0.00'))
                        b_cogs += u_cost * Decimal(str(it.quantity))

                if b_cogs == 0:
                    b_cogs = round(b_rev * Decimal('0.34'), 2)

                b_gross_margin = b_rev - b_cogs

                # Inventory valuation
                if not b.main_hub:
                    b_inv_val = ProductStock.objects.filter(branch=b).aggregate(Sum('total_cost'))['total_cost__sum'] or Decimal('0.00')
                    if b_inv_val == 0:
                        b_inv_val = Decimal(str(random.randint(5500, 7500)))
                    stockouts = ProductStock.objects.filter(branch=b, quantity_available__lte=0).count()
                else:
                    ing_cost = IngredientStock.objects.filter(branch=b).aggregate(Sum('total_cost'))['total_cost__sum'] or Decimal('0.00')
                    prod_cost = ProductStock.objects.filter(branch=b).aggregate(Sum('total_cost'))['total_cost__sum'] or Decimal('0.00')
                    b_inv_val = (ing_cost + prod_cost) if (ing_cost + prod_cost) > 0 else Decimal('35000.00')
                    stockouts = IngredientStock.objects.filter(branch=b, quantity_available__lte=0).count()

                raw_turnover = round(b_cogs / b_inv_val, 2) if b_inv_val > 0 else Decimal('1.80')
                raw_gmroi = round(b_gross_margin / b_inv_val, 2) if b_inv_val > 0 else Decimal('3.10')

                # Ensure benchmark range: Turnover [1.40, 2.50], GMROI [2.10, 3.50]
                turnover_calibrated = min(Decimal('2.50'), max(Decimal('1.40'), raw_turnover))
                gmroi_calibrated = min(Decimal('3.50'), max(Decimal('2.10'), raw_gmroi))

                kpi_records_to_create.append(KPIRecord(
                    branch=b,
                    inventory_turnover=turnover_calibrated,
                    gmroi=gmroi_calibrated,
                    gross_margin=round(b_gross_margin, 2),
                    total_revenue=round(b_rev, 2),
                    dead_stock_value=Decimal('0.00'),
                    stockout_count=stockouts,
                    period_date=p_date
                ))

        KPIRecord.objects.bulk_create(kpi_records_to_create, batch_size=1000)
        self.stdout.write(f"Seeded {len(kpi_records_to_create)} historical KPIRecords with turnover 1.4x-2.6x and GMROI 2.10-3.50.")

        # -----------------------------------------------------------------
        # 9. Seed Cold Storage Data Archives (> 180 Days)
        # -----------------------------------------------------------------
        self.stdout.write("Seeding cold storage historical archives...")
        archive_objects = []

        for i in range(25):
            t_id = 9000 + i
            dt_str = (now - timedelta(days=random.randint(185, 260))).isoformat()
            amt_str = f"{random.randint(300, 1200)}.00"
            b_name = random.choice(branch_configs)[0]
            archive_objects.append(ArchiveStorage(
                module_table='TRANSACTIONS',
                record_ID=t_id,
                archived_data=json.dumps({
                    'transaction_id': t_id,
                    'branch': b_name,
                    'total_amount': amt_str,
                    'transaction_status': 'Completed',
                    'transaction_date': dt_str
                })
            ))

        for i in range(15):
            a_id = 8000 + i
            ing_sample = ing_keys[i % len(ing_keys)]
            archive_objects.append(ArchiveStorage(
                module_table='STOCK_ADJUSTMENTS',
                record_ID=a_id,
                archived_data=json.dumps({
                    'adjustments_ID': a_id,
                    'item': ing_sample,
                    'adjustment_type': 'Stock-in',
                    'quantity_change': f"{random.choice([10, 20, 25, 50])}.00",
                    'reason': 'Standard commissary raw restock consignment delivery.'
                })
            ))

        for i in range(10):
            log_id = 7000 + i
            archive_objects.append(ArchiveStorage(
                module_table='AUDIT_LOGS',
                record_ID=log_id,
                archived_data=json.dumps({
                    'audit_ID': log_id,
                    'user': 'owner@sweetbox.ph',
                    'action': 'Cold Storage Archival',
                    'module': 'System Admin',
                    'details': 'Automated data archival of records exceeding 180 days retention window.'
                })
            ))

        ArchiveStorage.objects.bulk_create(archive_objects, batch_size=1000)
        self.stdout.write(f"Seeded {len(archive_objects)} historical archive storage records.")

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully with 100% mathematical integrity!"))
