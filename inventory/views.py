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
from .models import Ingredient, IngredientStock, BillOfMaterial, ConstraintParameter, ProductStock, StockAdjustment, RestockRequest
from pos.models import Product, ProductCategory
from accounts.models import Branch, AuditLog

class LiveStockView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        branch_filter = request.GET.get('branch', 'all')
        
        # Branch Filtering
        if getattr(user, 'role', '') == 'Business Owner' or user.is_superuser:
            stocks = IngredientStock.objects.all() if branch_filter == 'all' else IngredientStock.objects.filter(branch_id=branch_filter)
            prod_stocks = ProductStock.objects.all() if branch_filter == 'all' else ProductStock.objects.filter(branch_id=branch_filter)
        else:
            stocks = IngredientStock.objects.filter(branch=user.branch)
            prod_stocks = ProductStock.objects.filter(branch=user.branch)
            
        inventory_data, restock_queue, product_watch_data = [], [], []
        kpis = {'in_stock': 0, 'low_stock': 0, 'critical': 0, 'expiring': 0}
        thirty_days = timezone.now() + timedelta(days=30)
        
        # 1. Process Raw Ingredients
        for stock in stocks:
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
                
            first_bom = BillOfMaterial.objects.filter(ingredient=stock.ingredient).first()
            
            inventory_data.append({
                "id": stock.ingredient_inventory_ID,
                "ingredient_name": stock.ingredient.ingredient_name,
                "category": first_bom.product.category.category_name if first_bom and first_bom.product.category else "Uncategorized", 
                "unit": unit, "cost_per_unit": cost, "quantity": qty, "threshold": threshold,
                "branch": stock.branch.name, "expiry": stock.expiry_date.strftime('%Y-%m-%d') if stock.expiry_date else "N/A", "status": status_flag
            })
            
            if status_flag in ["Low Stock", "Critical"]:
                restock_queue.append({
                    "item": stock.ingredient.ingredient_name, "branch": stock.branch.name, "branch_id": stock.branch.branch_ID, "supplier": "Main Hub",
                    "order_amount": f"{threshold * 2}", "current": qty, "min": threshold
                })

        # 2. Process Pre-Made Products (Product Watch)
        for p_stock in prod_stocks:
            qty, threshold = p_stock.quantity_available, p_stock.low_stock_threshold
            
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
                "product_name": p_stock.product.product_name,
                "category": p_stock.product.category.category_name if p_stock.product.category else "Uncategorized",
                "price": float(p_stock.product.price), "quantity": qty, "threshold": threshold,
                "branch": p_stock.branch.name, "status": status_flag
            })

        # 3. BOM Data
        bom_data = [{"id": p.product_ID, "product": p.product_name, "category": p.category.category_name if p.category else "General", "ingredients": ", ".join([r.ingredient.ingredient_name for r in BillOfMaterial.objects.filter(product=p)]), "deductions": ", ".join([f"{float(r.quantity_required)}{r.measurement_unit} {r.ingredient.ingredient_name.split()[0].lower()}" for r in BillOfMaterial.objects.filter(product=p)])} for p in Product.objects.filter(is_active=True)]

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
            db_prescriptions = PrescriptiveOutput.objects.filter(status__in=['Pending Review', 'Flagged - Needs Override'])
        else:
            target_branch = branch_filter if branch_filter != 'all' else user.branch.branch_ID
            db_prescriptions = PrescriptiveOutput.objects.filter(branch_id=target_branch, status__in=['Pending Review', 'Flagged - Needs Override'])

        prescriptive_actions = [{
            "id": p.prescriptive_output_ID,
            "title": p.output_type,
            "description": p.recommendation,
            "impact": p.justification,
            "status": p.status,
            "color": "danger" if "Flagged" in p.status else "warning"
        } for p in db_prescriptions]

        return Response({
            "kpis": kpis, 
            "inventory": inventory_data, 
            "bom": bom_data, 
            "restock_queue": restock_queue, 
            "prescriptive_actions": prescriptive_actions, 
            "product_watch": product_watch_data, 
            "pending_restocks": pending_restocks
        })

class BOMCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        data = request.data
        try:
            category, _ = ProductCategory.objects.get_or_create(category_name=data.get('category', 'General'))
            product = Product.objects.create(category=category, product_name=data['product_name'], price=data.get('price', 0.00), is_active=True)
            
            for item in data.get('ingredients', []):
                ingredient, created = Ingredient.objects.get_or_create(
                    ingredient_name=item['name'],
                    defaults={
                        'measurement_unit': item.get('unit', 'unit'),
                        'cost_per_unit': 0.00
                    }
                )
                
                # FIX: If ingredient exists, override the old unit/cost with the new user input
                if not created:
                    ingredient.measurement_unit = item.get('unit', ingredient.measurement_unit)
                    ingredient.cost_per_unit = item.get('cost', ingredient.cost_per_unit)
                    ingredient.save()
                
                BillOfMaterial.objects.create(product=product, ingredient=ingredient, quantity_required=item['deduction'], measurement_unit=ingredient.measurement_unit)
                
                if created:
                    for branch in Branch.objects.all():
                        IngredientStock.objects.create(branch=branch, ingredient=ingredient, total_cost=0, quantity_available=0, reorder_threshold=10)
                        
            return Response({"message": f"BOM configured for {product.product_name}"}, status=status.HTTP_201_CREATED)
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
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 0))
        branch_id = request.data.get('branch_id')
        
        if not product_id or quantity <= 0 or not branch_id:
            return Response({"error": "Invalid production data provided."}, status=400)

        try:
            product = Product.objects.get(product_ID=product_id)
            
            # CRITICAL FIX: Changed 'id' to 'branch_ID' to match the database schema
            branch = Branch.objects.get(branch_ID=branch_id)
            
            # 1. Check and Deduct Ingredients via BOM
            boms = BillOfMaterial.objects.filter(product=product)
            if not boms.exists():
                return Response({"error": f"{product.product_name} has no Bill of Materials configured. Cannot produce."}, status=400)

            for bom in boms:
                total_deduction = float(bom.quantity_required) * quantity
                stock = IngredientStock.objects.filter(branch=branch, ingredient=bom.ingredient).first()
                
                if not stock:
                    return Response({"error": f"Missing {bom.ingredient.ingredient_name} inventory at {branch.name}."}, status=400)
                if float(stock.quantity_available) < total_deduction:
                    return Response({"error": f"Insufficient {bom.ingredient.ingredient_name}. Need {total_deduction}, but only have {stock.quantity_available}."}, status=400)
                
                # Apply the deduction
                stock.quantity_available -= Decimal(str(total_deduction))
                stock.save()

            # 2. Add to Pre-Made Product Watch
            prod_stock, created = ProductStock.objects.get_or_create(
                branch=branch, 
                product=product,
                defaults={'quantity_available': 0, 'low_stock_threshold': 5}
            )
            prod_stock.quantity_available += quantity
            prod_stock.save()

            return Response({"message": f"Successfully produced {quantity} {product.product_name}(s). Ingredients deducted."})
            
        except Exception as e:
            return Response({"error": str(e)}, status=500)

class ManualStockAdjustmentView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        item_type = request.data.get('item_type') # 'ingredient' or 'product'
        item_id = request.data.get('item_id')
        adj_type = request.data.get('adjustment_type') # 'Stock-in', 'Stock-out', 'Spoilage'
        qty_change = Decimal(str(request.data.get('quantity_change', 0)))
        reason = request.data.get('reason')

        if qty_change <= 0:
            return Response({"error": "Quantity must be greater than zero."}, status=400)
        if not reason:
            return Response({"error": "An adjustment reason is mandatory."}, status=400)

        try:
            adj_record = StockAdjustment(user=request.user, adjustment_type=adj_type, quantity_change=qty_change, reason=reason)
            
            if item_type == 'ingredient':
                stock = IngredientStock.objects.get(ingredient_inventory_ID=item_id)
                adj_record.ingredients_inventory = stock
                item_name = stock.ingredient.ingredient_name
            else:
                stock = ProductStock.objects.get(product_inventory_ID=item_id)
                adj_record.product_inventory = stock
                item_name = stock.product.product_name

            # Apply mathematical deduction/addition
            if adj_type == 'Stock-in':
                stock.quantity_available += qty_change
            else: # Stock-out or Spoilage
                if stock.quantity_available < qty_change:
                    return Response({"error": f"Cannot deduct {qty_change}. Only {stock.quantity_available} available."}, status=400)
                stock.quantity_available -= qty_change

            stock.save()
            adj_record.save()

            # Create immutable Audit Log
            AuditLog.objects.create(
                user=request.user, 
                action=f"Manual {adj_type}", 
                module="Inventory Management", 
                details=f"Adjusted {item_name} by {qty_change}. Reason: {reason}"
            )

            return Response({"message": f"Successfully updated {item_name} inventory."})

        except Exception as e:
            return Response({"error": str(e)}, status=400)

class SubmitRestockView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request):
        if request.user.role != 'Branch Manager':
            return Response({"error": "Access Denied: Only Branch Managers can submit restock requests."}, status=403)
        
        ingredient_name = request.data.get('ingredient_name')
        qty = Decimal(str(request.data.get('quantity')))
        dest_branch_id = request.data.get('branch_id')
        
        try:
            ingredient = Ingredient.objects.get(ingredient_name=ingredient_name)
            dest_branch = Branch.objects.get(branch_ID=dest_branch_id)
            main_hub = Branch.objects.get(main_hub=True)
            
            RestockRequest.objects.create(
                ingredient=ingredient, user=request.user, source_branch=main_hub,
                destination_branch=dest_branch, requested_quantity=qty, status='Pending'
            )
            
            AuditLog.objects.create(user=request.user, action="Restock Submitted", module="Inventory Management", details=f"Requested {qty} {ingredient.measurement_unit} of {ingredient_name} for {dest_branch.name}.")
            return Response({"message": "Restock request submitted to management."})
        except Exception as e:
            return Response({"error": str(e)}, status=400)

class ProcessRestockView(APIView):
    permission_classes = [IsAuthenticated]

    @db_transaction.atomic
    def post(self, request, restock_id):
        if request.user.role not in ['Business Owner']:
            return Response({"error": "Access Denied: Only the Business Owner can approve requests."}, status=403)
        
        action = request.data.get('action') 
        try:
            req = RestockRequest.objects.get(restock_ID=restock_id)
            if req.status != 'Pending':
                return Response({"error": "Request already processed."}, status=400)
                
            if action == 'Approve':
                # 1. Deduct from Main Hub
                source_stock = IngredientStock.objects.get(branch=req.source_branch, ingredient=req.ingredient)
                if source_stock.quantity_available < req.requested_quantity:
                    return Response({"error": "Main Hub has insufficient stock to fulfill this request."}, status=400)
                
                source_stock.quantity_available -= req.requested_quantity
                source_stock.save()
                
                # 2. Add to Satellite Branch
                dest_stock, _ = IngredientStock.objects.get_or_create(branch=req.destination_branch, ingredient=req.ingredient, defaults={'total_cost': 0, 'reorder_threshold': 10})
                dest_stock.quantity_available += req.requested_quantity
                dest_stock.save()
            
            req.status = action
            req.approved_by = request.user
            req.approved_at = timezone.now()
            req.request_finished = timezone.now()
            req.save()
            
            AuditLog.objects.create(user=request.user, action=f"Restock {action}", module="Inventory Management", details=f"{action}d transfer of {req.requested_quantity} {req.ingredient.ingredient_name} to {req.destination_branch.name}.")
            return Response({"message": f"Request {action.lower()}d successfully."})
        except Exception as e:
            return Response({"error": str(e)}, status=400)