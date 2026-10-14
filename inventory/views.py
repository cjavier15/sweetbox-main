from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import transaction as db_transaction
from django.db.models import ProtectedError
from django.utils import timezone
from datetime import timedelta
from analytics.models import PrescriptiveOutput
from .models import (
    Ingredient, IngredientStock, BillOfMaterial, ConstraintParameter, 
    ProductStock, StockAdjustment, RestockRequest, ProductTransfer
)
from pos.models import Product, ProductCategory
from accounts.models import Branch, AuditLog

class LiveStockView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        branch_filter = request.GET.get('branch', 'all')
        
        # Branch Filtering
        if getattr(user, 'role', '') == 'Business Owner' or user.is_superuser:
            stocks = IngredientStock.objects.select_related('ingredient__category', 'branch').all() if branch_filter == 'all' else IngredientStock.objects.select_related('ingredient__category', 'branch').filter(branch_id=branch_filter)
            prod_stocks = ProductStock.objects.select_related('product__category', 'branch').all() if branch_filter == 'all' else ProductStock.objects.select_related('product__category', 'branch').filter(branch_id=branch_filter)
        else:
            stocks = IngredientStock.objects.select_related('ingredient__category', 'branch').filter(branch=user.branch)
            prod_stocks = ProductStock.objects.select_related('product__category', 'branch').filter(branch=user.branch)
            
        inventory_data, restock_queue, product_watch_data = [], [], []
        kpis = {'in_stock': 0, 'low_stock': 0, 'critical': 0, 'expiring': 0}
        thirty_days = timezone.now() + timedelta(days=30)
        
        # 1. Process Raw Ingredients
        for stock in stocks:
            # Hub vs Satellite visibility rules:
            # Main hub (Ibaan): keep as is, all ingredients visible.
            # Other branches: only see ingredients outside Cake and Pastry categories.
            is_hub = bool(stock.branch and (stock.branch.main_hub or stock.branch.branch_ID == 1 or 'ibaan' in stock.branch.name.lower()))
            if not is_hub and stock.ingredient.is_cake_or_pastry():
                continue

            qty, threshold, unit, cost = float(stock.quantity_available), float(stock.reorder_threshold), stock.ingredient.measurement_unit, float(stock.ingredient.cost_per_unit)
            
            if qty <= (threshold * 0.5):
                status_flag = "Critical"
                kpis['critical'] += 1
            elif qty <= threshold:
                status_flag = "Low Stock"
                kpis['low_stock'] += 1
            else:
                status_flag = "In Stock"
                kpis['in_stock'] += 1
                
            if stock.expiry_date and stock.expiry_date <= thirty_days:
                status_flag = "Expiring Soon"
                kpis['expiring'] += 1
                
            ing_category = stock.ingredient.get_category_name()
            
            inventory_data.append({
                "id": stock.ingredient_inventory_ID,
                "ingredient_name": stock.ingredient.ingredient_name,
                "category": ing_category, 
                "unit": unit, "cost_per_unit": cost, "quantity": qty, "threshold": threshold,
                "branch": stock.branch.name, "branch_id": stock.branch.branch_ID,
                "expiry": stock.expiry_date.strftime('%Y-%m-%d') if stock.expiry_date else "N/A", "status": status_flag
            })
            
            if status_flag in ["Low Stock", "Critical"]:
                restock_queue.append({
                    "item": stock.ingredient.ingredient_name, "branch": stock.branch.name, "branch_id": stock.branch.branch_ID, "supplier": "Main Hub",
                    "order_amount": f"{threshold * 2}", "current": qty, "min": threshold
                })

        # 2. Process Pre-Made Products (Product Watch)
        for p_stock in prod_stocks:
            qty, threshold = float(p_stock.quantity_available), float(p_stock.reorder_threshold)
            
            if qty <= (threshold * 0.5):
                status_flag = "Critical"
                kpis['critical'] += 1
            elif qty <= threshold:
                status_flag = "Low Stock"
                kpis['low_stock'] += 1
            else:
                status_flag = "In Stock"
                
            product_watch_data.append({
                "id": p_stock.product_inventory_ID,
                "product_id": p_stock.product.product_ID,
                "product_name": p_stock.product.product_name,
                "category": p_stock.product.category.category_name if p_stock.product.category else "General",
                "price": float(p_stock.product.price), "quantity": qty, "threshold": threshold,
                "branch": p_stock.branch.name, "branch_id": p_stock.branch.branch_ID,
                "status": status_flag
            })

        # 3. BOM Data
        bom_data = []
        for p in Product.objects.filter(is_active=True).prefetch_related('bom_ingredients__ingredient', 'category'):
            recipes = list(p.bom_ingredients.all())
            ings = ", ".join([r.ingredient.ingredient_name for r in recipes]) if recipes else "No ingredients configured"
            deducts = ", ".join([f"{float(r.quantity_required)} {r.measurement_unit} {r.ingredient.ingredient_name.split()[0].lower()}" for r in recipes]) if recipes else "-"
            bom_data.append({
                "id": p.product_ID,
                "product": p.product_name,
                "category": p.category.category_name if p.category else "General",
                "ingredients": ings,
                "deductions": deducts
            })

        # 4. Pending Restock Approvals
        pending_qs = RestockRequest.objects.filter(status='Pending')
        if getattr(user, 'role', '') != 'Business Owner' and branch_filter == 'all':
             pending_qs = pending_qs.filter(destination_branch=user.branch)
        elif branch_filter != 'all':
            pending_qs = pending_qs.filter(destination_branch_id=branch_filter)
            
        pending_restocks = [{
            "id": r.restock_ID,
            "item": r.ingredient.ingredient_name if r.ingredient else r.product.product_name,
            "destination": r.destination_branch.name,
            "qty": float(r.requested_quantity),
            "user": r.user.name if r.user else "System"
        } for r in pending_qs]

        # 5. Fetch Actual AI Prescriptions
        if getattr(user, 'role', '') == 'Business Owner' and branch_filter == 'all':
            db_prescriptions = PrescriptiveOutput.objects.select_related('branch').filter(status__in=['Pending Review', 'Flagged - Needs Override'])
        else:
            target_branch = branch_filter if branch_filter != 'all' else (user.branch.branch_ID if user.branch else 1)
            db_prescriptions = PrescriptiveOutput.objects.select_related('branch').filter(branch_id=target_branch, status__in=['Pending Review', 'Flagged - Needs Override'])

        prescriptive_actions = [{
            "id": p.prescriptive_output_ID,
            "branch": p.branch.name if p.branch else "Headquarters",
            "branch_id": p.branch.branch_ID if p.branch else None,
            "title": p.output_type,
            "description": p.recommendation,
            "impact": p.justification,
            "status": p.status,
            "color": "danger" if "Flagged" in p.status else "warning"
        } for p in db_prescriptions]

        categories_data = [{
            "id": c.category_ID,
            "name": c.category_name
        } for c in ProductCategory.objects.all().order_by('category_name')]

        return Response({
            "kpis": kpis, 
            "inventory": inventory_data, 
            "bom": bom_data, 
            "restock_queue": restock_queue, 
            "prescriptive_actions": prescriptive_actions, 
            "product_watch": product_watch_data, 
            "pending_restocks": pending_restocks,
            "categories": categories_data
        })

class CategoryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        categories = ProductCategory.objects.all().order_by('category_name')
        return Response([{
            "id": c.category_ID,
            "name": c.category_name,
            "category_name": c.category_name,
            "description": c.description or ""
        } for c in categories], status=status.HTTP_200_OK)

class IngredientCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        data = request.data
        name = data.get('ingredient_name') or data.get('name')
        if not name or not str(name).strip():
            return Response({"error": "Ingredient name is required and cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        name = str(name).strip()
        if len(name) > 100:
            return Response({"error": "Ingredient name cannot exceed 100 characters."}, status=status.HTTP_400_BAD_REQUEST)
        if name.replace(' ', '').isdigit():
            return Response({"error": "Ingredient name cannot be purely numeric."}, status=status.HTTP_400_BAD_REQUEST)

        unit = str(data.get('measurement_unit') or data.get('unit', 'kg')).strip() or 'kg'

        try:
            raw_cost = data.get('cost_per_unit', data.get('cost', 0.00))
            if raw_cost is None or str(raw_cost).strip() == '':
                cost = Decimal('0.00')
            else:
                cost = Decimal(str(raw_cost))
            if cost < 0:
                return Response({"error": "Cost per unit cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)
            if cost > Decimal('100000.00'):
                return Response({"error": "Cost per unit cannot exceed ₱100,000.00."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Invalid cost per unit. Must be a valid non-negative number."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            raw_qty = data.get('initial_quantity', data.get('initial_stock', 0.00))
            if raw_qty is None or str(raw_qty).strip() == '':
                initial_qty = Decimal('0.00')
            else:
                initial_qty = Decimal(str(raw_qty))
            if initial_qty < 0:
                return Response({"error": "Initial quantity cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)
            if initial_qty > Decimal('50000.00'):
                return Response({"error": "Initial quantity cannot exceed 50,000 units."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Invalid initial quantity. Must be a valid non-negative number."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            raw_threshold = data.get('reorder_threshold', 10.00)
            if raw_threshold is None or str(raw_threshold).strip() == '':
                threshold = Decimal('10.00')
            else:
                threshold = Decimal(str(raw_threshold))
            if threshold < 0:
                return Response({"error": "Reorder threshold cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)
            if threshold > Decimal('10000.00'):
                return Response({"error": "Reorder threshold cannot exceed 10,000 units."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Invalid reorder threshold. Must be a valid non-negative number."}, status=status.HTTP_400_BAD_REQUEST)


        branch_id = data.get('branch_id')

        category_id = data.get('category_id')
        category_name = data.get('category') or data.get('category_name')
        category = None
        if category_id:
            category = ProductCategory.objects.filter(category_ID=category_id).first()
        elif category_name and str(category_name).strip():
            category = ProductCategory.objects.filter(category_name__iexact=str(category_name).strip()).first()
            if not category:
                category = ProductCategory.objects.create(category_name=str(category_name).strip())

        ingredient, created = Ingredient.objects.get_or_create(
            ingredient_name=name,
            defaults={
                'category': category,
                'measurement_unit': unit,
                'cost_per_unit': cost
            }
        )
        if not created:
            ingredient.measurement_unit = unit
            ingredient.cost_per_unit = cost
            if category:
                ingredient.category = category
            ingredient.save()
        elif category and not ingredient.category:
            ingredient.category = category
            ingredient.save()

        # Initialize stock across all branches
        target_branch = None
        if branch_id and str(branch_id) != 'all':
            target_branch = Branch.objects.filter(branch_ID=branch_id).first()
        if not target_branch:
            target_branch = Branch.objects.filter(main_hub=True).first() or Branch.objects.first()

        for branch in Branch.objects.all():
            qty = initial_qty if (branch == target_branch or branch_id == 'all') else Decimal('0.00')
            total_cost = qty * cost
            stock_obj, stock_created = IngredientStock.objects.get_or_create(
                branch=branch,
                ingredient=ingredient,
                defaults={
                    'quantity_available': qty,
                    'reorder_threshold': threshold,
                    'total_cost': total_cost
                }
            )
            if not stock_created and (branch == target_branch or branch_id == 'all') and initial_qty > 0:
                stock_obj.quantity_available += initial_qty
                stock_obj.total_cost += total_cost
                stock_obj.save()

            ConstraintParameter.objects.get_or_create(
                branch=branch,
                ingredient=ingredient,
                defaults={
                    'lead_time_days': 3,
                    'min_order_quantity': Decimal('5.00'),
                    'max_order_quantity': Decimal('200.00'),
                    'production_limit': Decimal('100.00'),
                    'capacity_limit': Decimal('500.00')
                }
            )

            # Audit trail: log stock adjustment if stock was allocated
            if qty > 0:
                StockAdjustment.objects.create(
                    user=request.user,
                    ingredients_inventory=stock_obj,
                    adjustment_type='Stock-in',
                    quantity_change=qty,
                    reason=f"Initial stock allocation for new ingredient '{ingredient.ingredient_name}' at {branch.name}."
                )

        AuditLog.objects.create(
            user=request.user,
            action="Ingredient Added",
            module="Inventory Management",
            details=f"Created ingredient {ingredient.ingredient_name} ({unit}) with initial stock {initial_qty} at {target_branch.name if target_branch else 'all branches'}."
        )

        return Response({
            "message": f"Ingredient '{ingredient.ingredient_name}' successfully added and initialized across branches.",
            "ingredient_ID": ingredient.ingredient_ID
        }, status=status.HTTP_201_CREATED)

class BOMCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        data = request.data
        try:
            prod_name = data.get('product_name')
            if not prod_name or not str(prod_name).strip():
                return Response({"error": "Product name is required."}, status=status.HTTP_400_BAD_REQUEST)
            prod_name = str(prod_name).strip()
            if len(prod_name) > 100:
                return Response({"error": "Product name cannot exceed 100 characters."}, status=status.HTTP_400_BAD_REQUEST)
            if prod_name.replace(' ', '').isdigit():
                return Response({"error": "Product name cannot be purely numeric."}, status=status.HTTP_400_BAD_REQUEST)

            cat_input = data.get('category') or data.get('category_name') or data.get('category_id') or 'General'
            category = None
            if isinstance(cat_input, int) or (isinstance(cat_input, str) and str(cat_input).isdigit()):
                category = ProductCategory.objects.filter(category_ID=int(cat_input)).first()
            if not category and cat_input:
                category = ProductCategory.objects.filter(category_name__iexact=str(cat_input).strip()).first()
            if not category:
                category, _ = ProductCategory.objects.get_or_create(category_name=str(cat_input).strip())

            try:
                price = Decimal(str(data.get('price', 0.00)))
                if price < 0:
                    return Response({"error": "Product price cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)
                if price > Decimal('100000.00'):
                    return Response({"error": "Product price cannot exceed ₱100,000.00."}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                return Response({"error": "Invalid price provided."}, status=status.HTTP_400_BAD_REQUEST)

            product = Product.objects.create(category=category, product_name=prod_name, price=price, is_active=True)
            
            for item in data.get('ingredients', []):
                ing_name = str(item.get('name', '')).strip()
                if not ing_name:
                    continue
                try:
                    ing_cost = Decimal(str(item.get('cost', 0.00)))
                    if ing_cost < 0:
                        ing_cost = Decimal('0.00')
                    elif ing_cost > Decimal('100000.00'):
                        ing_cost = Decimal('100000.00')
                except Exception:
                    ing_cost = Decimal('0.00')

                try:
                    deduction_qty = Decimal(str(item.get('deduction', 0.00)))
                    if deduction_qty <= 0:
                        return Response({"error": f"Deduction quantity for {ing_name} must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)
                    if deduction_qty > Decimal('10000.00'):
                        return Response({"error": f"Deduction quantity for {ing_name} cannot exceed 10,000 units."}, status=status.HTTP_400_BAD_REQUEST)
                except Exception:
                    return Response({"error": f"Invalid deduction quantity for {ing_name}."}, status=status.HTTP_400_BAD_REQUEST)

                ingredient, created = Ingredient.objects.get_or_create(
                    ingredient_name=ing_name,
                    defaults={
                        'measurement_unit': item.get('unit', 'unit'),
                        'cost_per_unit': ing_cost
                    }
                )
                
                if not created and 'cost' in item:
                    ingredient.measurement_unit = item.get('unit', ingredient.measurement_unit)
                    ingredient.cost_per_unit = ing_cost
                    ingredient.save()
                
                BillOfMaterial.objects.create(
                    product=product,
                    ingredient=ingredient,
                    quantity_required=deduction_qty,
                    measurement_unit=ingredient.measurement_unit
                )
                
                for branch in Branch.objects.all():
                    IngredientStock.objects.get_or_create(
                        branch=branch, ingredient=ingredient,
                        defaults={'total_cost': Decimal('0.00'), 'quantity_available': Decimal('0.00'), 'reorder_threshold': Decimal('10.00')}
                    )
                    ConstraintParameter.objects.get_or_create(
                        branch=branch, ingredient=ingredient,
                        defaults={
                            'lead_time_days': 3,
                            'min_order_quantity': Decimal('5.00'),
                            'max_order_quantity': Decimal('200.00'),
                            'production_limit': Decimal('100.00'),
                            'capacity_limit': Decimal('500.00')
                        }
                    )

            try:
                initial_stock = Decimal(str(data.get('initial_stock', data.get('initial_quantity', 0.00))))
                if initial_stock < 0:
                    initial_stock = Decimal('0.00')
                elif initial_stock > Decimal('50000.00'):
                    return Response({"error": "Initial stock cannot exceed 50,000 units."}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                initial_stock = Decimal('0.00')

            try:
                threshold = Decimal(str(data.get('reorder_threshold', 5.00)))
                if threshold < 0:
                    threshold = Decimal('5.00')
                elif threshold > Decimal('10000.00'):
                    return Response({"error": "Reorder threshold cannot exceed 10,000 units."}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                threshold = Decimal('5.00')


            for branch in Branch.objects.all():
                is_hub = bool(branch.main_hub or branch.branch_ID == 1 or 'ibaan' in branch.name.lower())
                ps_qty = initial_stock if is_hub else Decimal('0.00')
                p_stock, _ = ProductStock.objects.get_or_create(
                    branch=branch,
                    product=product,
                    defaults={
                        'quantity_available': ps_qty,
                        'reorder_threshold': threshold,
                        'total_cost': Decimal('0.00')
                    }
                )
                if ps_qty > 0:
                    StockAdjustment.objects.create(
                        user=request.user,
                        product_inventory=p_stock,
                        adjustment_type='Stock-in',
                        quantity_change=ps_qty,
                        reason=f"Initial finished stock for new product '{product.product_name}'."
                    )

                ConstraintParameter.objects.get_or_create(
                    branch=branch,
                    product=product,
                    defaults={
                        'lead_time_days': 1,
                        'min_order_quantity': Decimal('1.00'),
                        'max_order_quantity': Decimal('50.00'),
                        'production_limit': Decimal('50.00'),
                        'capacity_limit': Decimal('100.00')
                    }
                )

            AuditLog.objects.create(
                user=request.user,
                action="Product Configured",
                module="Inventory Management",
                details=f"Configured product '{product.product_name}' (₱{product.price}) with BOM and initialized branch stocks."
            )
                        
            return Response({"message": f"BOM configured for {product.product_name}. Initialized across all branches."}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ProductDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def delete(self, request, product_id):
        try:
            product = Product.objects.get(product_ID=product_id)
            product_name = product.product_name
            
            boms = BillOfMaterial.objects.filter(product=product)
            ingredients_to_check = [bom.ingredient for bom in boms]
            
            try:
                product.delete()
            except ProtectedError:
                product.is_active = False
                product.save()
                boms.delete()
                
            # FIX: Sweep and delete ingredients if no other active BOM uses them
            for ing in ingredients_to_check:
                if not BillOfMaterial.objects.filter(ingredient=ing).exists():
                    IngredientStock.objects.filter(ingredient=ing).delete()
                    ing.delete()
                    
            return Response({"message": f"{product_name} deleted successfully. Orphaned ingredients removed."})
        except Product.DoesNotExist:
            return Response({"error": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

class ProduceProductView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        user = request.user
        is_owner = (getattr(user, 'role', '') == 'Business Owner' or user.is_superuser)
        user_branch = getattr(user, 'branch', None)
        is_ibaan = bool(user_branch and (user_branch.main_hub or user_branch.branch_ID == 1 or 'ibaan' in user_branch.name.lower()))

        # Task 3: Restrict "Produce Product" to Main Hub Only
        # Only managers assigned to the Ibaan branch (or Business Owner / Superuser) can trigger the production action.
        if not (is_owner or is_ibaan):
            return Response(
                {"error": "Access Denied: Product manufacturing/production is strictly exclusive to the Main Hub (Ibaan) and Business Owner."},
                status=status.HTTP_403_FORBIDDEN
            )

        product_id = request.data.get('product_id')
        branch_id = request.data.get('branch_id')
        
        try:
            raw_qty = request.data.get('quantity', 0)
            quantity = int(raw_qty)
            if quantity <= 0:
                return Response({"error": "Production quantity must be an integer greater than zero."}, status=status.HTTP_400_BAD_REQUEST)
            if quantity > 10000:
                return Response({"error": "Production quantity cannot exceed 10,000 units per batch."}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({"error": "Invalid production quantity. Must be a valid positive integer."}, status=status.HTTP_400_BAD_REQUEST)

        if not product_id:
            return Response({"error": "Product ID is required for production."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(product_ID=product_id)
            
            # Target branch resolution: Production strictly occurs at the Main Production Hub (Ibaan)
            if is_owner:
                if branch_id and str(branch_id) != 'all':
                    branch = Branch.objects.filter(branch_ID=branch_id).first()
                else:
                    branch = Branch.objects.filter(main_hub=True).first() or Branch.objects.filter(branch_ID=1).first() or user_branch
            else:
                branch = user_branch
            
            if not branch:
                return Response({"error": "No valid production branch could be determined."}, status=status.HTTP_400_BAD_REQUEST)

            # Ensure the production location is Main Hub (Ibaan)
            is_target_hub = bool(branch.main_hub or branch.branch_ID == 1 or 'ibaan' in branch.name.lower())
            if not is_target_hub:
                return Response(
                    {"error": f"Production cannot occur at {branch.name}. Manufacturing is strictly exclusive to the Main Hub (Ibaan)."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # 1. Check and Deduct Ingredients via BOM with concurrency row-level lock
            boms = list(BillOfMaterial.objects.filter(product=product).select_related('ingredient'))
            if not boms:
                return Response({"error": f"{product.product_name} has no Bill of Materials configured. Cannot produce."}, status=status.HTTP_400_BAD_REQUEST)

            # First verify all ingredients are sufficient under lock before mutating
            ingredient_stocks_to_update = []
            for bom in boms:
                qty_req = Decimal(str(bom.quantity_required))
                qty_to_produce = Decimal(str(quantity))
                total_deduction = qty_req * qty_to_produce
                
                stock = IngredientStock.objects.select_for_update().filter(
                    branch=branch, ingredient=bom.ingredient
                ).first()
                if not stock:
                    stock = IngredientStock.objects.create(
                        branch=branch, ingredient=bom.ingredient,
                        quantity_available=Decimal('0.00'), reorder_threshold=Decimal('10.00'), total_cost=Decimal('0.00')
                    )
                    stock = IngredientStock.objects.select_for_update().get(pk=stock.pk)
                
                if stock.quantity_available < total_deduction:
                    return Response({
                        "error": f"Insufficient {bom.ingredient.ingredient_name} at {branch.name}. Need {total_deduction} {bom.measurement_unit}, but only have {stock.quantity_available} {bom.measurement_unit}."
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                ingredient_stocks_to_update.append((stock, bom, total_deduction))

            # Apply ingredient deductions
            for stock, bom, total_deduction in ingredient_stocks_to_update:
                if stock.quantity_available > 0 and stock.total_cost > 0:
                    cost_per_unit = stock.total_cost / stock.quantity_available
                    stock.total_cost = max(Decimal('0.00'), stock.total_cost - (cost_per_unit * total_deduction))
                stock.quantity_available -= total_deduction
                stock.save()

                StockAdjustment.objects.create(
                    user=user,
                    ingredients_inventory=stock,
                    adjustment_type='Stock-out',
                    quantity_change=total_deduction,
                    reason=f"Kitchen production of {quantity}x {product.product_name} at {branch.name}"
                )

            # 2. Add to Pre-Made Product Stock under row-level lock
            prod_stock = ProductStock.objects.select_for_update().filter(
                branch=branch, product=product
            ).first()
            if not prod_stock:
                prod_stock = ProductStock.objects.create(
                    branch=branch, 
                    product=product,
                    quantity_available=Decimal('0.00'), reorder_threshold=Decimal('5.00'), total_cost=Decimal('0.00')
                )
                prod_stock = ProductStock.objects.select_for_update().get(pk=prod_stock.pk)

            prod_stock.quantity_available += Decimal(str(quantity))
            prod_stock.save()

            StockAdjustment.objects.create(
                user=user,
                product_inventory=prod_stock,
                adjustment_type='Stock-in',
                quantity_change=Decimal(str(quantity)),
                reason=f"Kitchen production completed: {quantity}x {product.product_name} at {branch.name}"
            )

            AuditLog.objects.create(
                user=user,
                action="Kitchen Production",
                module="Inventory Management",
                details=f"Produced {quantity} {product.product_name} at {branch.name}. Ingredients deducted and product stock increased."
            )

            return Response(
                {"message": f"Successfully produced {quantity} {product.product_name}(s) at {branch.name}. Ingredients deducted and display stock added."},
                status=status.HTTP_201_CREATED
            )
            
        except Product.DoesNotExist:
            return Response({"error": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ManualStockAdjustmentView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        data = request.data
        item_type = data.get('item_type') # 'ingredient' or 'product'
        if item_type not in ['ingredient', 'product']:
            return Response({"error": "Invalid item type. Must be 'ingredient' or 'product'."}, status=status.HTTP_400_BAD_REQUEST)

        adj_type = data.get('adjustment_type', 'Stock-in') # 'Stock-in', 'Stock-out', 'Spoilage'
        if adj_type not in ['Stock-in', 'Stock-out', 'Spoilage']:
            return Response({"error": "Invalid adjustment type. Must be 'Stock-in', 'Stock-out', or 'Spoilage'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            raw_qty = data.get('quantity_change')
            if raw_qty is None or str(raw_qty).strip() == '':
                return Response({"error": "Quantity change is required."}, status=status.HTTP_400_BAD_REQUEST)
            qty_change = Decimal(str(raw_qty))
            if qty_change <= 0:
                return Response({"error": "Quantity change must be a positive number greater than zero."}, status=status.HTTP_400_BAD_REQUEST)
            if qty_change > Decimal('50000.00'):
                return Response({"error": "Quantity change cannot exceed 50,000 units."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Invalid quantity change. Must be a valid positive number."}, status=status.HTTP_400_BAD_REQUEST)

        reason = data.get('reason')
        if not reason or not str(reason).strip():
            return Response({"error": "An adjustment reason is mandatory and cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        reason = str(reason).strip()

        item_id = data.get('item_id')
        branch_id = data.get('branch_id')
        target_id = data.get('target_id')
        expiry_date = data.get('expiry_date')
        batch_number = data.get('batch_number')

        user = request.user
        is_owner = (getattr(user, 'role', '') == 'Business Owner' or user.is_superuser)

        try:
            adj_record = StockAdjustment(user=user, adjustment_type=adj_type, quantity_change=qty_change, reason=reason)
            
            if item_type == 'ingredient':
                if item_id:
                    stock = IngredientStock.objects.select_for_update().filter(ingredient_inventory_ID=item_id).first()
                elif branch_id and target_id:
                    branch = Branch.objects.filter(branch_ID=branch_id).first()
                    ingredient = Ingredient.objects.filter(ingredient_ID=target_id).first()
                    if not branch or not ingredient:
                        return Response({"error": "Branch or Ingredient does not exist."}, status=status.HTTP_404_NOT_FOUND)
                    stock = IngredientStock.objects.select_for_update().filter(branch=branch, ingredient=ingredient).first()
                    if not stock:
                        stock = IngredientStock.objects.create(
                            branch=branch, ingredient=ingredient,
                            quantity_available=Decimal('0.00'), reorder_threshold=Decimal('10.00'), total_cost=Decimal('0.00')
                        )
                        stock = IngredientStock.objects.select_for_update().get(pk=stock.pk)
                else:
                    return Response({"error": "Target ingredient could not be identified."}, status=status.HTTP_400_BAD_REQUEST)

                if not stock:
                    return Response({"error": "Ingredient stock record not found."}, status=status.HTTP_404_NOT_FOUND)

                # Branch isolation check: non-owner managers can only adjust stock for their assigned branch
                if not is_owner and user.branch and stock.branch_id != user.branch.branch_ID:
                    return Response({"error": "Access Denied: You cannot adjust inventory for another branch."}, status=status.HTTP_403_FORBIDDEN)

                adj_record.ingredients_inventory = stock
                item_name = stock.ingredient.ingredient_name
                
            else: # product
                if item_id:
                    stock = ProductStock.objects.select_for_update().filter(product_inventory_ID=item_id).first()
                elif branch_id and target_id:
                    branch = Branch.objects.filter(branch_ID=branch_id).first()
                    product = Product.objects.filter(product_ID=target_id).first()
                    if not branch or not product:
                        return Response({"error": "Branch or Product does not exist."}, status=status.HTTP_404_NOT_FOUND)
                    stock = ProductStock.objects.select_for_update().filter(branch=branch, product=product).first()
                    if not stock:
                        stock = ProductStock.objects.create(
                            branch=branch, product=product,
                            quantity_available=Decimal('0.00'), reorder_threshold=Decimal('5.00'), total_cost=Decimal('0.00')
                        )
                        stock = ProductStock.objects.select_for_update().get(pk=stock.pk)
                else:
                    return Response({"error": "Target product could not be identified."}, status=status.HTTP_400_BAD_REQUEST)

                if not stock:
                    return Response({"error": "Product stock record not found."}, status=status.HTTP_404_NOT_FOUND)

                # Branch isolation check
                if not is_owner and user.branch and stock.branch_id != user.branch.branch_ID:
                    return Response({"error": "Access Denied: You cannot adjust inventory for another branch."}, status=status.HTTP_403_FORBIDDEN)

                adj_record.product_inventory = stock
                item_name = stock.product.product_name

            # Apply mathematical deduction or addition with atomic row locking
            if adj_type == 'Stock-in':
                stock.quantity_available += qty_change
                if expiry_date:
                    stock.expiry_date = expiry_date
                if batch_number:
                    stock.batch_number = batch_number
                if 'cost' in data and data['cost'] is not None and str(data['cost']).strip() != '':
                    try:
                        cost_val = Decimal(str(data['cost']))
                        if cost_val < 0:
                            return Response({"error": "Cost cannot be negative."}, status=status.HTTP_400_BAD_REQUEST)
                        stock.total_cost += (cost_val * qty_change)
                    except Exception:
                        return Response({"error": "Invalid cost value provided."}, status=status.HTTP_400_BAD_REQUEST)
            else: # Stock-out or Spoilage
                if stock.quantity_available < qty_change:
                    return Response({"error": f"Cannot deduct {qty_change}. Only {stock.quantity_available} available in stock."}, status=status.HTTP_400_BAD_REQUEST)
                # Deduct proportional cost
                if stock.quantity_available > 0 and stock.total_cost > 0:
                    cost_per_unit = stock.total_cost / stock.quantity_available
                    stock.total_cost = max(Decimal('0.00'), stock.total_cost - (cost_per_unit * qty_change))
                stock.quantity_available -= qty_change

            stock.save()
            adj_record.save()

            # Create immutable Audit Log
            AuditLog.objects.create(
                user=user, 
                action=f"Manual {adj_type}", 
                module="Inventory Management", 
                details=f"Adjusted {item_name} at {stock.branch.name} by {qty_change} ({adj_type}). Reason: {reason}"
            )

            return Response({
                "message": f"Successfully updated {item_name} inventory ({adj_type}: {qty_change}).",
                "new_quantity": float(stock.quantity_available)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class SubmitRestockView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        if request.user.role != 'Branch Manager' and not request.user.is_superuser:
            return Response({"error": "Access Denied: Only Branch Managers can submit restock requests."}, status=status.HTTP_403_FORBIDDEN)
        
        item_type = request.data.get('item_type', 'ingredient') # 'ingredient' or 'product'
        item_name = request.data.get('ingredient_name') or request.data.get('product_name') or request.data.get('item_name')
        qty = Decimal(str(request.data.get('quantity', 0)))
        dest_branch_id = request.data.get('branch_id')
        
        if not item_name:
            return Response({"error": "Item name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if qty <= 0:
            return Response({"error": "Quantity must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            dest_branch = Branch.objects.get(branch_ID=dest_branch_id)
            main_hub = Branch.objects.get(main_hub=True)
            
            if dest_branch == main_hub:
                return Response({"error": "Destination branch cannot be the Main Hub."}, status=status.HTTP_400_BAD_REQUEST)

            if item_type == 'product':
                product = Product.objects.get(product_name=item_name)
                req = RestockRequest.objects.create(
                    product=product, user=request.user, source_branch=main_hub,
                    destination_branch=dest_branch, requested_quantity=qty, status='Pending'
                )
                unit_label = "units"
            else:
                ingredient = Ingredient.objects.get(ingredient_name=item_name)
                req = RestockRequest.objects.create(
                    ingredient=ingredient, user=request.user, source_branch=main_hub,
                    destination_branch=dest_branch, requested_quantity=qty, status='Pending'
                )
                unit_label = ingredient.measurement_unit
            
            AuditLog.objects.create(
                user=request.user, action="Restock Submitted", module="Inventory Management",
                details=f"Requested {qty} {unit_label} of {item_name} for {dest_branch.name}."
            )
            return Response({"message": f"Restock request for {item_name} ({qty} {unit_label}) submitted to management."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ProcessRestockView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request, restock_id):
        if request.user.role not in ['Business Owner'] and not request.user.is_superuser:
            return Response({"error": "Access Denied: Only the Business Owner can approve requests."}, status=status.HTTP_403_FORBIDDEN)
        
        action = request.data.get('action') # 'Approve' or 'Reject'
        try:
            req = RestockRequest.objects.get(restock_ID=restock_id)
            if req.status != 'Pending':
                return Response({"error": "Request has already been processed."}, status=status.HTTP_400_BAD_REQUEST)
                
            item_name = req.ingredient.ingredient_name if req.ingredient else req.product.product_name
            
            if action == 'Approve':
                if req.ingredient:
                    # 1. Deduct from Main Hub
                    source_stock = IngredientStock.objects.get(branch=req.source_branch, ingredient=req.ingredient)
                    if Decimal(str(source_stock.quantity_available)) < Decimal(str(req.requested_quantity)):
                        return Response({"error": f"Main Hub has insufficient stock of {item_name} (Available: {source_stock.quantity_available})."}, status=status.HTTP_400_BAD_REQUEST)
                    
                    source_stock.quantity_available = Decimal(str(source_stock.quantity_available)) - Decimal(str(req.requested_quantity))
                    source_stock.save()
                    
                    # 2. Add to Satellite Branch
                    dest_stock, _ = IngredientStock.objects.get_or_create(
                        branch=req.destination_branch, ingredient=req.ingredient,
                        defaults={'quantity_available': Decimal('0.00'), 'total_cost': Decimal('0.00'), 'reorder_threshold': Decimal('10.00')}
                    )
                    dest_stock.quantity_available = Decimal(str(dest_stock.quantity_available)) + Decimal(str(req.requested_quantity))
                    dest_stock.save()
                    
                else: # req.product
                    source_stock = ProductStock.objects.get(branch=req.source_branch, product=req.product)
                    if Decimal(str(source_stock.quantity_available)) < Decimal(str(req.requested_quantity)):
                        return Response({"error": f"Main Hub has insufficient stock of {item_name} (Available: {source_stock.quantity_available})."}, status=status.HTTP_400_BAD_REQUEST)
                        
                    source_stock.quantity_available = Decimal(str(source_stock.quantity_available)) - Decimal(str(req.requested_quantity))
                    source_stock.save()
                    
                    dest_stock, _ = ProductStock.objects.get_or_create(
                        branch=req.destination_branch, product=req.product,
                        defaults={'quantity_available': Decimal('0.00'), 'total_cost': Decimal('0.00'), 'reorder_threshold': Decimal('5.00')}
                    )
                    dest_stock.quantity_available = Decimal(str(dest_stock.quantity_available)) + Decimal(str(req.requested_quantity))
                    dest_stock.save()

                req.status = 'Approved'
            else:
                req.status = 'Rejected'

            req.approved_by = request.user
            req.approved_at = timezone.now()
            req.request_finished = timezone.now()
            req.save()
            
            AuditLog.objects.create(
                user=request.user, 
                action=f"Restock {req.status}", 
                module="Inventory Management", 
                details=f"{req.status} transfer of {req.requested_quantity} {item_name} to {req.destination_branch.name}."
            )
            return Response({"message": f"Request {req.status.lower()} successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ProductTransferView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_owner = (getattr(user, 'role', '') == 'Business Owner' or user.is_superuser)
        user_branch = getattr(user, 'branch', None)
        is_main_hub = bool(user_branch and (user_branch.main_hub or user_branch.branch_ID == 1 or 'ibaan' in user_branch.name.lower()))

        if not (is_owner or is_main_hub):
            return Response(
                {"error": "Access Denied: Product transfers can only be viewed or performed by the Business Owner or Main Production Hub (Ibaan)."},
                status=status.HTTP_403_FORBIDDEN
            )

        transfers = ProductTransfer.objects.select_related(
            'product', 'source_branch', 'destination_branch', 'transferred_by'
        ).order_by('-transfer_date')[:50]

        transfers_data = [{
            "id": t.transfer_ID,
            "product_id": t.product.product_ID,
            "product_name": t.product.product_name,
            "source_branch": t.source_branch.name,
            "destination_branch": t.destination_branch.name,
            "destination_branch_id": t.destination_branch.branch_ID,
            "quantity": float(t.quantity),
            "transferred_by": t.transferred_by.name if t.transferred_by else "System",
            "transfer_date": t.transfer_date.strftime('%Y-%m-%d %H:%M'),
            "notes": t.notes or ""
        } for t in transfers]

        branches = [{
            "id": b.branch_ID,
            "name": b.name,
            "is_hub": bool(b.main_hub or b.branch_ID == 1 or 'ibaan' in b.name.lower())
        } for b in Branch.objects.all().order_by('branch_ID')]

        return Response({
            "transfers": transfers_data,
            "branches": branches
        }, status=status.HTTP_200_OK)

    @db_transaction.atomic
    def post(self, request):
        user = request.user
        is_owner = (getattr(user, 'role', '') == 'Business Owner' or user.is_superuser)
        user_branch = getattr(user, 'branch', None)
        is_main_hub = bool(user_branch and (user_branch.main_hub or user_branch.branch_ID == 1 or 'ibaan' in user_branch.name.lower()))

        if not (is_owner or is_main_hub):
            return Response(
                {"error": "Access Denied: Inter-branch product transfers can only be performed by the Business Owner or Main Production Hub (Ibaan)."},
                status=status.HTTP_403_FORBIDDEN
            )

        data = request.data
        product_id = data.get('product_id')
        product_name = data.get('product_name')
        dest_branch_id = data.get('destination_branch_id')
        source_branch_id = data.get('source_branch_id')
        notes = data.get('notes', '').strip()

        try:
            qty = Decimal(str(data.get('quantity', 0)))
        except Exception:
            return Response({"error": "Invalid quantity provided."}, status=status.HTTP_400_BAD_REQUEST)

        if qty <= 0:
            return Response({"error": "Transfer quantity must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)
        if qty > Decimal('50000.00'):
            return Response({"error": "Transfer quantity cannot exceed 50,000 units."}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve Source Branch
        if is_main_hub and not is_owner:
            source_branch = user_branch
        elif source_branch_id:
            source_branch = Branch.objects.filter(branch_ID=source_branch_id).first()
            if not source_branch:
                return Response({"error": "Specified source branch does not exist."}, status=status.HTTP_400_BAD_REQUEST)
        elif user_branch:
            source_branch = user_branch
        else:
            source_branch = Branch.objects.filter(main_hub=True).first() or Branch.objects.filter(branch_ID=1).first()

        # Resolve Destination Branch
        if not dest_branch_id:
            return Response({"error": "Destination branch is required for product transfer."}, status=status.HTTP_400_BAD_REQUEST)

        dest_branch = Branch.objects.filter(branch_ID=dest_branch_id).first()
        if not dest_branch:
            return Response({"error": "Destination branch does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        if source_branch.branch_ID == dest_branch.branch_ID:
            return Response({"error": "Source and destination branch cannot be the same."}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve Product
        product = None
        if product_id:
            product = Product.objects.filter(product_ID=product_id).first()
        elif product_name:
            product = Product.objects.filter(product_name__iexact=str(product_name).strip()).first()

        if not product:
            return Response({"error": "Selected product does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        # Concurrency Lock & Stock Check on Source Branch
        source_stock = ProductStock.objects.select_for_update().filter(
            branch=source_branch, product=product
        ).first()

        if not source_stock or source_stock.quantity_available < qty:
            available = float(source_stock.quantity_available) if source_stock else 0.0
            return Response(
                {"error": f"Insufficient stock of '{product.product_name}' at {source_branch.name}. Available: {available}, Requested: {float(qty)}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Deduct from Source
        source_stock.quantity_available -= qty
        source_stock.save()

        # Add to Destination
        dest_stock, _ = ProductStock.objects.select_for_update().get_or_create(
            branch=dest_branch,
            product=product,
            defaults={
                'quantity_available': Decimal('0.00'),
                'reorder_threshold': Decimal('5.00'),
                'total_cost': Decimal('0.00')
            }
        )
        dest_stock.quantity_available += qty
        dest_stock.save()

        # Create ProductTransfer record
        transfer = ProductTransfer.objects.create(
            product=product,
            source_branch=source_branch,
            destination_branch=dest_branch,
            quantity=qty,
            transferred_by=user,
            notes=notes
        )

        # Create Stock Adjustment records for audit trail
        StockAdjustment.objects.create(
            user=user,
            product_inventory=source_stock,
            adjustment_type='Transfer-Out',
            quantity_change=-qty,
            reason=f"Inter-branch transfer #{transfer.transfer_ID} to {dest_branch.name}. {notes}".strip()
        )
        StockAdjustment.objects.create(
            user=user,
            product_inventory=dest_stock,
            adjustment_type='Transfer-In',
            quantity_change=qty,
            reason=f"Inter-branch transfer #{transfer.transfer_ID} from {source_branch.name}. {notes}".strip()
        )

        # Audit Log
        AuditLog.objects.create(
            user=user,
            action="Product Transfer",
            module="Inventory Management",
            details=f"Transferred {qty} units of '{product.product_name}' from {source_branch.name} to {dest_branch.name} (Transfer #{transfer.transfer_ID})."
        )

        return Response({
            "message": f"Successfully transferred {qty} units of '{product.product_name}' from {source_branch.name} to {dest_branch.name}.",
            "transfer_ID": transfer.transfer_ID,
            "source_branch": source_branch.name,
            "destination_branch": dest_branch.name,
            "product_name": product.product_name,
            "quantity": float(qty),
            "source_available": float(source_stock.quantity_available),
            "dest_available": float(dest_stock.quantity_available)
        }, status=status.HTTP_200_OK)