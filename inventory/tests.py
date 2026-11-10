from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User, Branch, AuditLog
from pos.models import Product, ProductCategory
from inventory.models import (
    Ingredient, IngredientStock, ProductStock, BillOfMaterial, 
    RestockRequest, ProductTransfer, StockAdjustment, ConstraintParameter
)
from analytics.models import PrescriptiveOutput
from analytics.services import (
    _generate_rule_based_prescriptions,
    _generate_satellite_prescriptions,
    generate_restock_directive,
)

class InventoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hub = Branch.objects.create(name="Ibaan (Main Hub)", address="Hub St", main_hub=True)
        self.branch = Branch.objects.create(name="Branch 1", address="Branch St", main_hub=False)
        self.owner = User.objects.create(name="Owner", email="owner_inv@sweetbox.ph", role="Business Owner", is_active=True)
        self.manager = User.objects.create(name="Manager", email="manager_inv@sweetbox.ph", role="Branch Manager", branch=self.branch, is_active=True)
        self.hub_manager = User.objects.create(name="Hub Manager", email="hubmanager_inv@sweetbox.ph", role="Branch Manager", branch=self.hub, is_active=True)
        self.staff = User.objects.create(name="Staff", email="staff_inv@sweetbox.ph", role="Staff", branch=self.branch, is_active=True)

        self.category = ProductCategory.objects.create(category_name="Cakes")
        self.product = Product.objects.create(category=self.category, product_name="Chocolate Cake", price=500.00, is_active=True)
        self.flour = Ingredient.objects.create(ingredient_name="Flour", measurement_unit="kg", cost_per_unit=Decimal('50.00'))
        self.sugar = Ingredient.objects.create(ingredient_name="Sugar", measurement_unit="kg", cost_per_unit=Decimal('40.00'))

        BillOfMaterial.objects.create(product=self.product, ingredient=self.flour, quantity_required=Decimal('2.00'), measurement_unit="kg")
        BillOfMaterial.objects.create(product=self.product, ingredient=self.sugar, quantity_required=Decimal('1.00'), measurement_unit="kg")

        self.flour_stock = IngredientStock.objects.create(branch=self.hub, ingredient=self.flour, quantity_available=Decimal('100.00'), total_cost=Decimal('5000.00'), reorder_threshold=Decimal('10.00'))
        self.sugar_stock = IngredientStock.objects.create(branch=self.hub, ingredient=self.sugar, quantity_available=Decimal('50.00'), total_cost=Decimal('2000.00'), reorder_threshold=Decimal('10.00'))

    def test_product_stock_defaults(self):
        ps = ProductStock.objects.create(branch=self.branch, product=self.product)
        self.assertEqual(ps.quantity_available, 0)
        self.assertEqual(ps.reorder_threshold, 5)

    def test_produce_product_view_success(self):
        self.client.force_authenticate(user=self.owner)
        payload = {
            'product_id': self.product.product_ID,
            'quantity': 5,
            'branch_id': self.hub.branch_ID
        }
        response = self.client.post('/api/inventory/produce/', payload, format='json')
        self.assertEqual(response.status_code, 201)

        # Flour: 100 - (5 * 2) = 90
        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.quantity_available, Decimal('90.00'))

        # ProductStock should be created/updated to 5
        ps = ProductStock.objects.get(branch=self.hub, product=self.product)
        self.assertEqual(ps.quantity_available, 5)

    def test_produce_product_view_insufficient_ingredients(self):
        self.client.force_authenticate(user=self.owner)
        payload = {
            'product_id': self.product.product_ID,
            'quantity': 100, # Requires 200kg flour, only 100kg available
            'branch_id': self.hub.branch_ID
        }
        response = self.client.post('/api/inventory/produce/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient", response.data.get('error', ''))

    def test_produce_product_view_satellite_branch_manager_rejected(self):
        """Satellite branch managers cannot produce products (strictly exclusive to Main Hub)."""
        self.client.force_authenticate(user=self.manager)
        payload = {
            'product_id': self.product.product_ID,
            'quantity': 2,
            'branch_id': self.branch.branch_ID
        }
        response = self.client.post('/api/inventory/produce/', payload, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertIn("Main Hub", response.data.get('error', ''))

    def test_produce_product_view_main_hub_manager(self):
        """Branch manager assigned to Main Hub (Ibaan) can successfully produce products."""
        self.client.force_authenticate(user=self.hub_manager)
        payload = {
            'product_id': self.product.product_ID,
            'quantity': 4,
            'branch_id': self.hub.branch_ID
        }
        response = self.client.post('/api/inventory/produce/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIn("produced 4", response.data.get('message', ''))

        # Hub flour deducted: 100 - (4 * 2) = 92
        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.quantity_available, Decimal('92.00'))

        # Hub sugar deducted: 50 - (4 * 1) = 46
        self.sugar_stock.refresh_from_db()
        self.assertEqual(self.sugar_stock.quantity_available, Decimal('46.00'))

        # Hub product stock increased to 4
        hub_ps = ProductStock.objects.get(branch=self.hub, product=self.product)
        self.assertEqual(hub_ps.quantity_available, Decimal('4.00'))

    def test_manual_stock_adjustment_view_success(self):
        self.client.force_authenticate(user=self.owner)
        payload = {
            'item_type': 'ingredient',
            'item_id': self.flour_stock.ingredient_inventory_ID,
            'adjustment_type': 'Stock-in',
            'quantity_change': 25,
            'reason': 'Fresh supplier delivery'
        }
        response = self.client.post('/api/inventory/adjust/', payload, format='json')
        self.assertEqual(response.status_code, 200)

        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.quantity_available, Decimal('125.00'))
        self.assertTrue(AuditLog.objects.filter(action="Manual Stock-in").exists())

    def test_manual_stock_adjustment_insufficient_stock(self):
        self.client.force_authenticate(user=self.owner)
        payload = {
            'item_type': 'ingredient',
            'item_id': self.flour_stock.ingredient_inventory_ID,
            'adjustment_type': 'Stock-out',
            'quantity_change': 500, # only 100 available
            'reason': 'Test over-deduction'
        }
        response = self.client.post('/api/inventory/adjust/', payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_submit_restock_branch_manager_only(self):
        # Staff should be rejected
        self.client.force_authenticate(user=self.staff)
        payload = {
            'product_name': 'Chocolate Cake',
            'quantity': 10,
            'branch_id': self.branch.branch_ID
        }
        response = self.client.post('/api/inventory/restock/submit/', payload, format='json')
        self.assertEqual(response.status_code, 403)

        # Satellite Branch Manager should be accepted for finished products
        self.client.force_authenticate(user=self.manager)
        response = self.client.post('/api/inventory/restock/submit/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(RestockRequest.objects.filter(product=self.product, destination_branch=self.branch).exists())

        # Satellite Branch Manager requesting raw ingredient must be rejected with 400 Bad Request
        ing_payload = {
            'ingredient_name': 'Flour',
            'quantity': 10,
            'branch_id': self.branch.branch_ID
        }
        ing_response = self.client.post('/api/inventory/restock/submit/', ing_payload, format='json')
        self.assertEqual(ing_response.status_code, 400)
        self.assertIn("Satellite branches can only request finished Cake & Pastry products", ing_response.data['error'])

        # Hub Manager requesting raw ingredient for Hub should be accepted
        hub_payload = {
            'ingredient_name': 'Flour',
            'quantity': 10,
            'branch_id': self.hub.branch_ID
        }
        self.client.force_authenticate(user=self.hub_manager)
        hub_response = self.client.post('/api/inventory/restock/submit/', hub_payload, format='json')
        self.assertEqual(hub_response.status_code, 200)
        self.assertTrue(RestockRequest.objects.filter(ingredient=self.flour, destination_branch=self.hub).exists())

    def test_ingredient_create_view_initializes_branches(self):
        """Test adding a new ingredient dynamically initializes IngredientStock across all branches."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            'ingredient_name': 'Matcha Powder',
            'measurement_unit': 'kg',
            'cost_per_unit': 350.00,
            'initial_quantity': 20.00,
            'reorder_threshold': 5.00,
            'branch_id': self.hub.branch_ID
        }
        response = self.client.post('/api/inventory/ingredient/add/', payload, format='json')
        self.assertEqual(response.status_code, 201)

        matcha = Ingredient.objects.get(ingredient_name='Matcha Powder')
        self.assertEqual(matcha.cost_per_unit, Decimal('350.00'))

        # Check stock initialized exclusively at hub, satellite has 0 rows
        hub_stock = IngredientStock.objects.get(branch=self.hub, ingredient=matcha)
        self.assertEqual(hub_stock.quantity_available, Decimal('20.00'))
        self.assertFalse(IngredientStock.objects.filter(branch=self.branch, ingredient=matcha).exists())

    def test_bom_create_view_initializes_product_stocks(self):
        """Test creating a new product with BOM automatically creates ProductStock for branches."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            'product_name': 'Matcha Chiffon Cake',
            'category': 'Cakes',
            'price': 600.00,
            'initial_stock': 8,
            'reorder_threshold': 4,
            'ingredients': [
                {'name': 'Flour', 'unit': 'kg', 'deduction': 0.50, 'cost': 50.00},
                {'name': 'Sugar', 'unit': 'kg', 'deduction': 0.30, 'cost': 40.00}
            ]
        }
        response = self.client.post('/api/inventory/bom/create/', payload, format='json')
        self.assertEqual(response.status_code, 201)

        product = Product.objects.get(product_name='Matcha Chiffon Cake')
        self.assertEqual(product.price, Decimal('600.00'))

        # ProductStock should be created for hub and branch
        hub_stock = ProductStock.objects.get(branch=self.hub, product=product)
        self.assertEqual(hub_stock.quantity_available, Decimal('8.00'))
        branch_stock = ProductStock.objects.get(branch=self.branch, product=product)
        self.assertEqual(branch_stock.quantity_available, Decimal('0.00'))

    def test_process_restock_ingredient_and_product(self):
        """Test owner approving a restock request transfers stock from hub to branch."""
        self.client.force_authenticate(user=self.owner)

        # 1. Ingredient restock
        req_ing = RestockRequest.objects.create(
            ingredient=self.flour, user=self.manager, source_branch=self.hub,
            destination_branch=self.branch, requested_quantity=Decimal('25.00'), status='Pending'
        )
        res = self.client.post(f'/api/inventory/restock/process/{req_ing.restock_ID}/', {'action': 'Approve'}, format='json')
        self.assertEqual(res.status_code, 200)

        # Hub: 100 - 25 = 75
        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.quantity_available, Decimal('75.00'))
        # Branch: 0 + 25 = 25
        branch_flour = IngredientStock.objects.get(branch=self.branch, ingredient=self.flour)
        self.assertEqual(branch_flour.quantity_available, Decimal('25.00'))

        # 2. Product restock
        hub_prod_stock = ProductStock.objects.create(branch=self.hub, product=self.product, quantity_available=15)
        branch_prod_stock = ProductStock.objects.create(branch=self.branch, product=self.product, quantity_available=2)
        req_prod = RestockRequest.objects.create(
            product=self.product, user=self.manager, source_branch=self.hub,
            destination_branch=self.branch, requested_quantity=Decimal('5.00'), status='Pending'
        )
        res_prod = self.client.post(f'/api/inventory/restock/process/{req_prod.restock_ID}/', {'action': 'Approve'}, format='json')
        self.assertEqual(res_prod.status_code, 200)

        hub_prod_stock.refresh_from_db()
        self.assertEqual(hub_prod_stock.quantity_available, Decimal('10.00'))
        branch_prod_stock.refresh_from_db()
        self.assertEqual(branch_prod_stock.quantity_available, Decimal('7.00'))

    def test_process_restock_reject(self):
        """Test owner rejecting restock request does not alter stocks."""
        self.client.force_authenticate(user=self.owner)
        req = RestockRequest.objects.create(
            ingredient=self.flour, user=self.manager, source_branch=self.hub,
            destination_branch=self.branch, requested_quantity=Decimal('10.00'), status='Pending'
        )
        res = self.client.post(f'/api/inventory/restock/process/{req.restock_ID}/', {'action': 'Reject'}, format='json')
        self.assertEqual(res.status_code, 200)

        req.refresh_from_db()
        self.assertEqual(req.status, 'Rejected')
        self.assertEqual(req.approved_by, self.owner)
        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.quantity_available, Decimal('100.00'))
        self.assertTrue(AuditLog.objects.filter(action="Rejected Restock Request").exists())

    def test_submit_restock_business_owner_forbidden(self):
        """Business Owners approve restock requests rather than submitting them (Req 13/14)."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            'product_name': 'Chocolate Cake',
            'quantity': 5,
            'branch_id': self.branch.branch_ID
        }
        res = self.client.post('/api/inventory/restock/submit/', payload, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertIn("Business Owners approve restock requests rather than submitting them.", res.data['error'])

    def test_hub_cannot_request_product_restock(self):
        """Main Hub produces products and cannot request product restock dispatches."""
        self.client.force_authenticate(user=self.hub_manager)
        payload = {
            'product_name': 'Chocolate Cake',
            'quantity': 5,
            'branch_id': self.hub.branch_ID
        }
        res = self.client.post('/api/inventory/restock/submit/', payload, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn("Main Hub (Ibaan) produces products on-site", res.data['error'])

    def test_owner_restock_dashboard_has_no_suggestions_and_only_satellite_dispatches(self):
        """Owner's dashboard has empty restock_queue and pending_restocks contains only satellite dispatches."""
        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/inventory/stock/?branch=all')
        self.assertEqual(res.status_code, 200)
        # Owner restock queue has zero suggestions (Owner never submits requests)
        self.assertEqual(len(res.data.get('restock_queue', [])), 0)

        # All pending restocks must be Product Dispatches for satellite branches
        for req in res.data.get('pending_restocks', []):
            self.assertEqual(req['item_type'], 'Product Dispatch')
            self.assertNotEqual(req['branch_id'], self.hub.branch_ID)

    def test_submit_restock_deduplicates_and_updates_qty(self):
        """Submitting duplicate restock request updates requested_quantity on existing pending request."""
        self.client.force_authenticate(user=self.manager)
        payload = {
            'product_name': 'Chocolate Cake',
            'quantity': 5,
            'branch_id': self.branch.branch_ID
        }
        res1 = self.client.post('/api/inventory/restock/submit/', payload, format='json')
        self.assertEqual(res1.status_code, 200)
        req1 = RestockRequest.objects.get(product=self.product, destination_branch=self.branch, status='Pending')
        self.assertEqual(req1.requested_quantity, Decimal('5.00'))

        # Submit another 7 units
        payload['quantity'] = 7
        res2 = self.client.post('/api/inventory/restock/submit/', payload, format='json')
        self.assertEqual(res2.status_code, 200)
        req1.refresh_from_db()
        self.assertEqual(req1.requested_quantity, Decimal('12.00'))
        self.assertEqual(RestockRequest.objects.filter(product=self.product, destination_branch=self.branch, status='Pending').count(), 1)

    def test_process_restock_branch_manager_forbidden(self):
        """Branch Managers must NEVER be able to approve or reject restock requests (Req 14)."""
        req = RestockRequest.objects.create(
            ingredient=self.flour, user=self.manager, source_branch=self.hub,
            destination_branch=self.branch, requested_quantity=Decimal('10.00'), status='Pending'
        )
        self.client.force_authenticate(user=self.manager)
        res_app = self.client.post(f'/api/inventory/restock/process/{req.restock_ID}/', {'action': 'Approve'}, format='json')
        self.assertEqual(res_app.status_code, 403)
        self.assertIn("Only the Business Owner can approve or reject restock requests", res_app.data['error'])

        res_rej = self.client.post(f'/api/inventory/restock/process/{req.restock_ID}/', {'action': 'Reject'}, format='json')
        self.assertEqual(res_rej.status_code, 403)

    def test_process_restock_approval_logs_audit_and_adjustments(self):
        """Owner approval increments destination stock, logs Restock Approved StockAdjustment, and AuditLog."""
        self.client.force_authenticate(user=self.owner)
        req = RestockRequest.objects.create(
            ingredient=self.flour, user=self.manager, source_branch=self.hub,
            destination_branch=self.branch, requested_quantity=Decimal('20.00'), status='Pending'
        )
        res = self.client.post(f'/api/inventory/restock/process/{req.restock_ID}/', {'action': 'approve'}, format='json')
        self.assertEqual(res.status_code, 200)

        req.refresh_from_db()
        self.assertEqual(req.status, 'Approved')
        self.assertEqual(req.approved_by, self.owner)
        self.assertIsNotNone(req.approved_at)

        # Verify StockAdjustment
        adj = StockAdjustment.objects.filter(adjustment_type='Restock Approved', quantity_change=Decimal('20.00')).first()
        self.assertIsNotNone(adj)

        # Verify AuditLog
        audit = AuditLog.objects.filter(action='Approved Restock Request', module='Inventory').first()
        self.assertIsNotNone(audit)
        self.assertIn(f"restock #{req.restock_ID}", audit.details)

    def test_manual_stock_adjustment_product_in_and_out(self):
        """Test stock-in and stock-out on product stock."""
        self.client.force_authenticate(user=self.owner)
        ps = ProductStock.objects.create(branch=self.branch, product=self.product, quantity_available=Decimal('10.00'))

        # Stock-in 5
        payload_in = {
            'item_type': 'product',
            'item_id': ps.product_inventory_ID,
            'adjustment_type': 'Stock-in',
            'quantity_change': 5,
            'reason': 'Fresh bakery batch'
        }
        res_in = self.client.post('/api/inventory/adjust/', payload_in, format='json')
        self.assertEqual(res_in.status_code, 200)
        ps.refresh_from_db()
        self.assertEqual(ps.quantity_available, Decimal('15.00'))

        # Stock-out 3
        payload_out = {
            'item_type': 'product',
            'item_id': ps.product_inventory_ID,
            'adjustment_type': 'Stock-out',
            'quantity_change': 3,
            'reason': 'Sampling promo'
        }
        res_out = self.client.post('/api/inventory/adjust/', payload_out, format='json')
        self.assertEqual(res_out.status_code, 200)
        ps.refresh_from_db()
        self.assertEqual(ps.quantity_available, Decimal('12.00'))

    def test_manual_stock_adjustment_dynamic_target_creation(self):
        """Test adjust endpoint dynamically creates/updates stock record at Main Hub if lookup is by branch_id and target_id."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            'item_type': 'ingredient',
            'branch_id': self.hub.branch_ID,
            'target_id': self.sugar.ingredient_ID,
            'adjustment_type': 'Stock-in',
            'quantity_change': 50,
            'reason': 'Direct hub delivery'
        }
        res = self.client.post('/api/inventory/adjust/', payload, format='json')
        self.assertEqual(res.status_code, 200)

        self.sugar_stock.refresh_from_db()
        self.assertEqual(self.sugar_stock.quantity_available, Decimal('100.00'))

        # Adjusting raw ingredient for satellite branch MUST return 403 Forbidden
        satellite_payload = {
            'item_type': 'ingredient',
            'branch_id': self.branch.branch_ID,
            'target_id': self.sugar.ingredient_ID,
            'adjustment_type': 'Stock-in',
            'quantity_change': 50,
            'reason': 'Direct branch delivery'
        }
        sat_res = self.client.post('/api/inventory/adjust/', satellite_payload, format='json')
        self.assertEqual(sat_res.status_code, 403)
        self.assertIn("centralized at Ibaan (Main Hub)", sat_res.data['error'])

    def test_branch_stock_visibility_hub_vs_satellite(self):
        """Test that main hub sees all ingredients, while satellite branches have empty raw ingredients and track ProductStock."""
        coffee_cat = ProductCategory.objects.create(category_name="Coffee")
        coffee_beans = Ingredient.objects.create(
            ingredient_name="Coffee Beans", category=coffee_cat, measurement_unit="kg", cost_per_unit=Decimal('300.00')
        )
        IngredientStock.objects.create(branch=self.hub, ingredient=coffee_beans, quantity_available=Decimal('20.00'))
        ProductStock.objects.create(branch=self.branch, product=self.product, quantity_available=Decimal('10.00'))

        # Hub Staff / Owner: can see all raw ingredients at hub
        hub_staff = User.objects.create(name="Hub Staff", email="hubstaff@sweetbox.ph", role="Staff", branch=self.hub, is_active=True)
        self.client.force_authenticate(user=hub_staff)
        res_hub = self.client.get('/api/inventory/stock/')
        self.assertEqual(res_hub.status_code, 200)
        hub_items = [i['ingredient_name'] for i in res_hub.data['inventory']]
        self.assertIn("Flour", hub_items)
        self.assertIn("Sugar", hub_items)
        self.assertIn("Coffee Beans", hub_items)

        # Satellite Branch Staff: MUST see 0 raw materials, is_satellite_branch=True, and track finished products in Product Watch
        self.client.force_authenticate(user=self.staff)
        res_branch = self.client.get('/api/inventory/stock/')
        self.assertEqual(res_branch.status_code, 200)
        self.assertTrue(res_branch.data['is_satellite_branch'])
        self.assertEqual(len(res_branch.data['inventory']), 0)
        pw_items = [p['product_name'] for p in res_branch.data['product_watch']]
        self.assertIn("Chocolate Cake", pw_items)

    def test_product_transfer_success_by_owner_and_hub(self):
        """Test inter-branch product transfer correctly deducts from hub and adds to destination branch."""
        hub_cake_stock = ProductStock.objects.create(
            branch=self.hub, product=self.product, quantity_available=Decimal('25.00')
        )
        branch_cake_stock = ProductStock.objects.create(
            branch=self.branch, product=self.product, quantity_available=Decimal('3.00')
        )

        self.client.force_authenticate(user=self.owner)
        payload = {
            'source_branch_id': self.hub.branch_ID,
            'destination_branch_id': self.branch.branch_ID,
            'product_id': self.product.product_ID,
            'quantity': 7,
            'notes': 'Morning delivery van #1'
        }
        response = self.client.post('/api/inventory/transfer/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn("Successfully transferred 7", response.data['message'])

        # Hub stock: 25 - 7 = 18
        hub_cake_stock.refresh_from_db()
        self.assertEqual(hub_cake_stock.quantity_available, Decimal('18.00'))

        # Destination branch stock: 3 + 7 = 10
        branch_cake_stock.refresh_from_db()
        self.assertEqual(branch_cake_stock.quantity_available, Decimal('10.00'))

        # Check ProductTransfer record
        transfer = ProductTransfer.objects.get(transfer_ID=response.data['transfer_ID'])
        self.assertEqual(transfer.quantity, Decimal('7.00'))
        self.assertEqual(transfer.source_branch, self.hub)
        self.assertEqual(transfer.destination_branch, self.branch)
        self.assertEqual(transfer.transferred_by, self.owner)
        self.assertEqual(transfer.notes, 'Morning delivery van #1')

        # Check StockAdjustment records
        adj_out = StockAdjustment.objects.filter(product_inventory=hub_cake_stock, adjustment_type='Transfer-Out').first()
        self.assertIsNotNone(adj_out)
        self.assertEqual(adj_out.quantity_change, Decimal('-7.00'))

        adj_in = StockAdjustment.objects.filter(product_inventory=branch_cake_stock, adjustment_type='Transfer-In').first()
        self.assertIsNotNone(adj_in)
        self.assertEqual(adj_in.quantity_change, Decimal('7.00'))

    def test_product_transfer_unauthorized_satellite_branch(self):
        """Test satellite branch users cannot initiate product transfers."""
        self.client.force_authenticate(user=self.manager)
        payload = {
            'source_branch_id': self.hub.branch_ID,
            'destination_branch_id': self.branch.branch_ID,
            'product_id': self.product.product_ID,
            'quantity': 5
        }
        response = self.client.post('/api/inventory/transfer/', payload, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertIn("Access Denied", response.data['error'])

    def test_product_transfer_insufficient_stock(self):
        """Test transfer fails with 400 when source hub has insufficient stock."""
        ProductStock.objects.create(
            branch=self.hub, product=self.product, quantity_available=Decimal('2.00')
        )
        self.client.force_authenticate(user=self.owner)
        payload = {
            'source_branch_id': self.hub.branch_ID,
            'destination_branch_id': self.branch.branch_ID,
            'product_id': self.product.product_ID,
            'quantity': 10
        }
        response = self.client.post('/api/inventory/transfer/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient stock", response.data['error'])

    def test_product_transfer_same_branch_rejected(self):
        """Test transfer cannot have same source and destination branch."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            'source_branch_id': self.hub.branch_ID,
            'destination_branch_id': self.hub.branch_ID,
            'product_id': self.product.product_ID,
            'quantity': 5
        }
        response = self.client.post('/api/inventory/transfer/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be the same", response.data['error'])

    def test_manual_stock_adjustment_invalid_inputs(self):
        """Ensure non-positive quantity, empty reason, or invalid adjustment type are rejected."""
        self.client.force_authenticate(user=self.owner)

        # Zero quantity
        res = self.client.post('/api/inventory/adjust/', {
            'item_type': 'ingredient',
            'item_id': self.flour_stock.ingredient_inventory_ID,
            'adjustment_type': 'Stock-in',
            'quantity_change': 0,
            'reason': 'Zero test'
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn("greater than zero", res.data.get('error', ''))

        # Negative quantity
        res = self.client.post('/api/inventory/adjust/', {
            'item_type': 'ingredient',
            'item_id': self.flour_stock.ingredient_inventory_ID,
            'adjustment_type': 'Stock-in',
            'quantity_change': -5,
            'reason': 'Negative test'
        }, format='json')
        self.assertEqual(res.status_code, 400)

        # Empty reason
        res = self.client.post('/api/inventory/adjust/', {
            'item_type': 'ingredient',
            'item_id': self.flour_stock.ingredient_inventory_ID,
            'adjustment_type': 'Stock-in',
            'quantity_change': 5,
            'reason': '   '
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn("reason", res.data.get('error', '').lower())

        # Invalid adjustment type
        res = self.client.post('/api/inventory/adjust/', {
            'item_type': 'ingredient',
            'item_id': self.flour_stock.ingredient_inventory_ID,
            'adjustment_type': 'MagicType',
            'quantity_change': 5,
            'reason': 'Type test'
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_ingredient_create_invalid_inputs(self):
        """Ensure negative costs/initial quantities and empty names are rejected."""
        self.client.force_authenticate(user=self.owner)

        # Negative cost
        res = self.client.post('/api/inventory/ingredient/add/', {
            'ingredient_name': 'Vanilla',
            'cost_per_unit': -10.00,
            'initial_quantity': 5,
            'branch_id': self.hub.branch_ID
        }, format='json')
        self.assertEqual(res.status_code, 400)

        # Empty name
        res = self.client.post('/api/inventory/ingredient/add/', {
            'ingredient_name': '   ',
            'cost_per_unit': 10.00,
            'initial_quantity': 5,
            'branch_id': self.hub.branch_ID
        }, format='json')
        self.assertEqual(res.status_code, 400)

    def test_category_list_api(self):
        """Test GET /api/inventory/categories/ returns active product categories."""
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/inventory/categories/')
        self.assertEqual(response.status_code, 200)
        names = [c['category_name'] for c in response.data]
        self.assertIn("Cakes", names)

    def test_manual_stock_adjustment_attribute_updates_ingredient(self):
        """Test editing ingredient attributes (name, category, unit, cost, threshold, batch, expiry)."""
        baking_cat = ProductCategory.objects.create(category_name="Baking Supplies")
        self.client.force_authenticate(user=self.owner)
        payload = {
            'item_type': 'ingredient',
            'item_id': self.flour_stock.ingredient_inventory_ID,
            'adjustment_mode': 'attribute_only',
            'name': 'Premium Bread Flour',
            'category': 'Baking Supplies',
            'measurement_unit': 'kg',
            'cost_per_unit': 65.50,
            'reorder_threshold': 15.00,
            'batch_number': 'BATCH-FLOUR-99',
            'expiry_date': '2027-01-01',
            'reason': 'Supplier rebranding and formula upgrade'
        }
        res = self.client.post('/api/inventory/adjust/', payload, format='json')
        self.assertEqual(res.status_code, 200)

        self.flour.refresh_from_db()
        self.flour_stock.refresh_from_db()

        self.assertEqual(self.flour.ingredient_name, 'Premium Bread Flour')
        self.assertEqual(self.flour.category.category_name, 'Baking Supplies')
        self.assertEqual(self.flour.cost_per_unit, Decimal('65.50'))
        self.assertEqual(self.flour_stock.reorder_threshold, Decimal('15.00'))
        self.assertEqual(self.flour_stock.batch_number, 'BATCH-FLOUR-99')
        self.assertEqual(self.flour_stock.quantity_available, Decimal('100.00')) # Unchanged

        # Check Audit Log
        audit = AuditLog.objects.filter(module="Inventory Management", action="Item Attribute Edit").last()
        self.assertIsNotNone(audit)
        self.assertIn("Premium Bread Flour", audit.details)

    def test_manual_stock_adjustment_direct_count_override(self):
        """Test direct physical count override sets exact stock and logs Direct Count Audit."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            'item_type': 'ingredient',
            'item_id': self.flour_stock.ingredient_inventory_ID,
            'adjustment_mode': 'direct',
            'direct_quantity': 82.50,
            'reason': 'Monthly physical count verification'
        }
        res = self.client.post('/api/inventory/adjust/', payload, format='json')
        self.assertEqual(res.status_code, 200)

        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.quantity_available, Decimal('82.50'))

        adj = StockAdjustment.objects.filter(
            ingredients_inventory=self.flour_stock,
            adjustment_type='Direct Count Audit'
        ).last()
        self.assertIsNotNone(adj)
        self.assertEqual(adj.quantity_change, Decimal('17.50')) # 100 - 82.50 = 17.50
        self.assertIn("Monthly physical count", adj.reason)

    def test_manual_stock_adjustment_attribute_and_price_product(self):
        """Test editing product attributes (name, category, price, threshold) without changing stock."""
        pastry_cat = ProductCategory.objects.create(category_name="Pastries")
        ps = ProductStock.objects.create(
            branch=self.hub, product=self.product, quantity_available=Decimal('20.00'), reorder_threshold=Decimal('5.00')
        )
        self.client.force_authenticate(user=self.owner)
        payload = {
            'item_type': 'product',
            'item_id': ps.product_inventory_ID,
            'adjustment_mode': 'none',
            'name': 'Dark Chocolate Truffle Cake',
            'category': 'Pastries',
            'price': 650.00,
            'reorder_threshold': 8.00,
            'reason': 'Menu price adjustment & rebranding'
        }
        res = self.client.post('/api/inventory/adjust/', payload, format='json')
        self.assertEqual(res.status_code, 200)

        self.product.refresh_from_db()
        ps.refresh_from_db()

        self.assertEqual(self.product.product_name, 'Dark Chocolate Truffle Cake')
        self.assertEqual(self.product.price, Decimal('650.00'))
        self.assertEqual(self.product.category.category_name, 'Pastries')
        self.assertEqual(ps.reorder_threshold, Decimal('8.00'))
        self.assertEqual(ps.quantity_available, Decimal('20.00'))

    def test_bom_update_view_success(self):
        """Test updating an existing product's BOM recipe, price, and category via BOMUpdateView."""
        self.client.force_authenticate(user=self.owner)
        cocoa = Ingredient.objects.create(ingredient_name="Cocoa Powder", measurement_unit="kg", cost_per_unit=Decimal('120.00'))

        payload = {
            'product_name': 'Deluxe Chocolate Cake',
            'category': 'Cakes',
            'price': 720.00,
            'reorder_threshold': 10.00,
            'ingredients': [
                {'name': 'Premium Bread Flour', 'unit': 'kg', 'deduction': 1.50},
                {'name': 'Cocoa Powder', 'unit': 'kg', 'deduction': 0.75}
            ]
        }
        res = self.client.post(f'/api/inventory/bom/update/{self.product.product_ID}/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn("Successfully updated BOM", res.data['message'])

        self.product.refresh_from_db()
        self.assertEqual(self.product.product_name, 'Deluxe Chocolate Cake')
        self.assertEqual(self.product.price, Decimal('720.00'))

        # Check BOM ingredients
        boms = list(BillOfMaterial.objects.filter(product=self.product).order_by('ingredient__ingredient_name'))
        self.assertEqual(len(boms), 2)
        bom_names = [b.ingredient.ingredient_name for b in boms]
        self.assertIn("Cocoa Powder", bom_names)
        self.assertIn("Premium Bread Flour", bom_names)
        self.assertNotIn("Sugar", bom_names) # Sugar was removed in updated recipe

    def test_live_stock_view_restock_and_prescription_deduplication(self):
        """Test LiveStockView returns product_id/ingredient_id in pending_restocks and deduplicates against AI prescriptions."""
        self.client.force_authenticate(user=self.owner)

        # Create a pending RestockRequest for Chocolate Cake at satellite branch
        RestockRequest.objects.create(
            product=self.product,
            destination_branch=self.branch,
            source_branch=self.hub,
            requested_quantity=Decimal('8.00'),
            user=self.manager,
            status='Pending'
        )

        # Create an AI prescription for the same item at the same branch
        PrescriptiveOutput.objects.create(
            branch=self.branch,
            product=self.product,
            output_type='Dispatch Transfer Prescription',
            recommendation='Dispatch 8 units of Chocolate Cake',
            justification='Low stock detected',
            recommended_quantity=Decimal('8.00'),
            status='Pending Review'
        )

        # Create another AI prescription for a different item without a pending restock
        other_prod = Product.objects.create(category=self.category, product_name="Strawberry Cake", price=600.00, is_active=True)
        po_other = PrescriptiveOutput.objects.create(
            branch=self.branch,
            product=other_prod,
            output_type='Dispatch Transfer Prescription',
            recommendation='Dispatch 5 units of Strawberry Cake',
            justification='Anticipating demand',
            recommended_quantity=Decimal('5.00'),
            status='Pending Review'
        )

        res = self.client.get(f'/api/inventory/stock/?branch={self.branch.branch_ID}')
        self.assertEqual(res.status_code, 200)

        # Verify pending_restocks contains product_id
        pending = res.data.get('pending_restocks', [])
        self.assertTrue(len(pending) > 0)
        prod_ids = [p.get('product_id') for p in pending]
        self.assertIn(self.product.product_ID, prod_ids)

        # Verify prescriptive_actions excludes Chocolate Cake (already has pending request) and includes Strawberry Cake
        prescriptions = res.data.get('prescriptive_actions', [])
        p_ids = [p.get('id') for p in prescriptions]
        self.assertIn(po_other.prescriptive_output_ID, p_ids)
        # Ensure Chocolate Cake prescription was excluded due to deduplication
        choc_prescriptions = [p for p in prescriptions if 'chocolate' in p.get('title', '').lower() or 'chocolate' in p.get('recommendation', '').lower()]
        self.assertEqual(len(choc_prescriptions), 0)

    def test_live_stock_view_includes_constraint_defaults_and_persisted_values(self):
        """Test LiveStockView attaches default and persisted ConstraintParameter fields on inventory and product_watch items."""
        ps = ProductStock.objects.create(
            branch=self.branch, product=self.product,
            quantity_available=Decimal('3.00'), reorder_threshold=Decimal('7.00')
        )
        cp_flour = ConstraintParameter.objects.create(
            branch=self.hub, ingredient=self.flour,
            lead_time_days=4, min_order_quantity=Decimal('10.00'),
            max_order_quantity=Decimal('40.00'), production_limit=Decimal('35.00'),
            capacity_limit=Decimal('120.00')
        )

        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/inventory/stock/?branch=all')
        self.assertEqual(res.status_code, 200)

        flour_row = next(x for x in res.data['inventory'] if x['id'] == self.flour_stock.ingredient_inventory_ID)
        sugar_row = next(x for x in res.data['inventory'] if x['id'] == self.sugar_stock.ingredient_inventory_ID)
        cake_row = next(x for x in res.data['product_watch'] if x['id'] == ps.product_inventory_ID)

        # Persisted ConstraintParameter for flour
        self.assertEqual(flour_row['constraint_id'], cp_flour.constraint_ID)
        self.assertEqual(flour_row['lead_time_days'], 4)
        self.assertEqual(flour_row['min_order_quantity'], 10.0)
        self.assertEqual(flour_row['max_order_quantity'], 40.0)
        self.assertEqual(flour_row['production_limit'], 35.0)
        self.assertEqual(flour_row['capacity_limit'], 120.0)
        self.assertEqual(flour_row['reorder_threshold'], 10.0)

        # Defaults when ConstraintParameter does not exist (sugar ingredient & cake product)
        for row, expected_thresh in [(sugar_row, 10.0), (cake_row, 7.0)]:
            self.assertIsNone(row['constraint_id'])
            self.assertEqual(row['lead_time_days'], 2)
            self.assertEqual(row['min_order_quantity'], 5.0)
            self.assertEqual(row['max_order_quantity'], 25.0)
            self.assertEqual(row['production_limit'], 20.0)
            self.assertEqual(row['capacity_limit'], 30.0)
            self.assertEqual(row['reorder_threshold'], expected_thresh)

    def test_update_constraint_parameters_permissions_and_persistence(self):
        """Test RBAC, atomic updates, audit logging, and product/ingredient target resolution."""
        sys_admin = User.objects.create(
            name="SysAdmin", email="sysadmin_inv@sweetbox.ph", role="System Administrator", is_active=True
        )
        ps = ProductStock.objects.create(
            branch=self.branch, product=self.product,
            quantity_available=Decimal('4.00'), reorder_threshold=Decimal('5.00')
        )

        # Staff -> 403
        self.client.force_authenticate(user=self.staff)
        res_staff = self.client.post('/api/inventory/constraints/update/', {
            'product_stock_id': ps.product_inventory_ID,
            'reorder_threshold': 6,
            'lead_time_days': 2,
            'min_order_quantity': 4,
            'max_order_quantity': 12,
            'production_limit': 10,
            'capacity_limit': 20
        }, format='json')
        self.assertEqual(res_staff.status_code, 403)

        # Satellite manager attempting to edit Hub ingredient -> 403
        self.client.force_authenticate(user=self.manager)
        res_cross = self.client.post('/api/inventory/constraints/update/', {
            'ingredient_stock_id': self.flour_stock.ingredient_inventory_ID,
            'reorder_threshold': 12,
            'lead_time_days': 3,
            'min_order_quantity': 6,
            'max_order_quantity': 30,
            'production_limit': 25,
            'capacity_limit': 60
        }, format='json')
        self.assertEqual(res_cross.status_code, 403)

        # Satellite manager updating own branch product -> 200
        res_mgr = self.client.post('/api/inventory/constraints/update/', {
            'product_stock_id': ps.product_inventory_ID,
            'reorder_threshold': 8.00,
            'lead_time_days': 3,
            'min_order_quantity': 4.00,
            'max_order_quantity': 16.00,
            'production_limit': 12.00,
            'capacity_limit': 24.00
        }, format='json')
        self.assertEqual(res_mgr.status_code, 200)
        ps.refresh_from_db()
        self.assertEqual(ps.reorder_threshold, Decimal('8.00'))
        cp_prod = ConstraintParameter.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(cp_prod.lead_time_days, 3)
        self.assertEqual(cp_prod.min_order_quantity, Decimal('4.00'))
        self.assertEqual(cp_prod.max_order_quantity, Decimal('16.00'))
        self.assertEqual(cp_prod.production_limit, Decimal('12.00'))
        self.assertEqual(cp_prod.capacity_limit, Decimal('24.00'))

        # Verify AuditLog contract
        audit = AuditLog.objects.filter(action='Updated AI Constraint Parameters', module='Inventory').last()
        self.assertIsNotNone(audit)
        self.assertIn('Chocolate Cake', audit.details)

        # System Administrator updating Hub ingredient via branch_id + ingredient_id -> 200
        self.client.force_authenticate(user=sys_admin)
        res_admin = self.client.post('/api/inventory/constraints/update/', {
            'branch_id': self.hub.branch_ID,
            'ingredient_id': self.flour.ingredient_ID,
            'reorder_threshold': 15.00,
            'lead_time_days': 5,
            'min_order_quantity': 8.00,
            'max_order_quantity': 35.00,
            'production_limit': 30.00,
            'capacity_limit': 100.00
        }, format='json')
        self.assertEqual(res_admin.status_code, 200)
        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.reorder_threshold, Decimal('15.00'))
        cp_ing = ConstraintParameter.objects.get(branch=self.hub, ingredient=self.flour)
        self.assertEqual(cp_ing.lead_time_days, 5)
        self.assertEqual(cp_ing.capacity_limit, Decimal('100.00'))

    def test_update_constraint_parameters_validation_rejects_invalid_bounds(self):
        """Test strict validation on lead time, positivity, MOQ <= Max Order <= Capacity Limit."""
        self.client.force_authenticate(user=self.owner)
        base = {
            'ingredient_stock_id': self.flour_stock.ingredient_inventory_ID,
            'reorder_threshold': 10,
            'lead_time_days': 2,
            'min_order_quantity': 5,
            'max_order_quantity': 25,
            'production_limit': 20,
            'capacity_limit': 30
        }

        invalid_cases = [
            {'reorder_threshold': -1},
            {'lead_time_days': 0},
            {'lead_time_days': 2.5},
            {'min_order_quantity': 0},
            {'min_order_quantity': 30, 'max_order_quantity': 25}, # max < min
            {'production_limit': 0},
            {'max_order_quantity': 35, 'capacity_limit': 30}, # capacity < max
        ]
        for patch in invalid_cases:
            payload = {**base, **patch}
            res = self.client.post('/api/inventory/constraints/update/', payload, format='json')
            self.assertEqual(res.status_code, 400, f"Expected 400 for patch {patch}, got {res.status_code}")

    def test_constraint_sensitivity_immediately_affects_ai_analysis(self):
        """Phase 5 verification: Updating ConstraintParameter immediately changes bounded AI prescription qty."""
        self.flour_stock.quantity_available = Decimal('2.00')
        self.flour_stock.reorder_threshold = Decimal('10.00')
        self.flour_stock.save()

        self.client.force_authenticate(user=self.owner)
        # Tightly constrain flour to max_order=12, capacity=10 -> available space = 10 - 2 = 8
        res_upd = self.client.post('/api/inventory/constraints/update/', {
            'ingredient_stock_id': self.flour_stock.ingredient_inventory_ID,
            'reorder_threshold': 10.00,
            'lead_time_days': 3,
            'min_order_quantity': 4.00,
            'max_order_quantity': 12.00,
            'production_limit': 20.00,
            'capacity_limit': 12.00
        }, format='json')
        self.assertEqual(res_upd.status_code, 200)

        res_ing = _generate_rule_based_prescriptions(self.hub, [self.flour_stock])
        po = PrescriptiveOutput.objects.get(prescriptive_output_ID=res_ing['outputs'][0])
        # Room available is 12 - 2 = 10.00; unbounded demand (15 days * burn) exceeds 10, so bounded qty must be 10.00
        self.assertGreaterEqual(float(po.recommended_quantity), 4.0)
        self.assertLessEqual(float(po.recommended_quantity), 10.0)

        # Satellite product constraint sensitivity check
        ps = ProductStock.objects.create(
            branch=self.branch, product=self.product,
            quantity_available=Decimal('2.00'), reorder_threshold=Decimal('10.00')
        )
        res_prod_upd = self.client.post('/api/inventory/constraints/update/', {
            'product_stock_id': ps.product_inventory_ID,
            'reorder_threshold': 10.00,
            'lead_time_days': 2,
            'min_order_quantity': 3.00,
            'max_order_quantity': 9.00,
            'production_limit': 8.00,
            'capacity_limit': 12.00
        }, format='json')
        self.assertEqual(res_prod_upd.status_code, 200)

        res_sat = _generate_satellite_prescriptions(self.branch)
        po_sat = PrescriptiveOutput.objects.get(prescriptive_output_ID=res_sat['outputs'][0])
        self.assertGreaterEqual(float(po_sat.recommended_quantity), 3.0)
        self.assertLessEqual(float(po_sat.recommended_quantity), 8.0)

    def test_prescriptive_directive_classification_and_balanced_hub_mix(self):
        """Ensure All Branches and Ibaan Main Hub Views serialize balanced procure/produce/dispatch directives without duplication."""
        self.flour_stock.quantity_available = Decimal('2.00')
        self.flour_stock.reorder_threshold = Decimal('10.00')
        self.flour_stock.save()

        # Low finished cake stock at Ibaan Main Hub (with BOM)
        ProductStock.objects.create(
            branch=self.hub, product=self.product,
            quantity_available=Decimal('1.00'), reorder_threshold=Decimal('6.00')
        )

        # Low finished cake stock at satellite branch (different product so RestockRequest seed doesn't mask it)
        strawberry_cake = Product.objects.create(
            category=self.category, product_name="Strawberry Cake", price=620.00, is_active=True
        )
        ProductStock.objects.create(
            branch=self.branch, product=strawberry_cake,
            quantity_available=Decimal('1.00'), reorder_threshold=Decimal('5.00')
        )

        self.client.force_authenticate(user=self.owner)

        for url in ['/api/inventory/stock/?branch=all', f'/api/inventory/stock/?branch={self.hub.branch_ID}']:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200)
            actions = res.data.get('prescriptive_actions', [])
            cats = {a.get('directive_category') for a in actions}
            badges = {a.get('directive_badge') for a in actions}
            self.assertEqual(cats, {'procure', 'produce', 'dispatch'}, f"Missing category on {url}: {cats}")
            self.assertEqual(badges, {'Procure Ingredient', 'Kitchen Production', 'Branch Dispatch'})

        # Running Run AI Analysis twice should update pending prescriptions in-place without duplicates
        res_ai_1 = self.client.post('/api/analytics/restock-directive/', {'branch_id': 'all'}, format='json')
        self.assertEqual(res_ai_1.status_code, 200)
        count_after_first = PrescriptiveOutput.objects.filter(status='Pending Review').count()

        res_ai_2 = self.client.post('/api/analytics/restock-directive/', {'branch_id': 'all'}, format='json')
        self.assertEqual(res_ai_2.status_code, 200)
        count_after_second = PrescriptiveOutput.objects.filter(status='Pending Review').count()
        self.assertEqual(count_after_first, count_after_second)

    def test_prescriptive_classification_rules_and_satellite_isolation(self):
        """Verify product outputs at Hub classify as produce while satellite outputs classify as dispatch, with satellite isolation."""
        extra_cake = Product.objects.create(
            category=self.category, product_name="Mocha Cake", price=550.00, is_active=True
        )
        po_hub_prod = PrescriptiveOutput.objects.create(
            branch=self.hub,
            product=extra_cake,
            output_type='Restock Prescription',
            recommendation='Replenish Mocha Cake commissary display',
            justification='Low hub cake inventory',
            recommended_quantity=Decimal('6.00'),
            status='Pending Review',
        )
        po_sat_prod = PrescriptiveOutput.objects.create(
            branch=self.branch,
            product=extra_cake,
            output_type='Restock Prescription',
            recommendation='Replenish Mocha Cake counter stock',
            justification='Low satellite cake inventory',
            recommended_quantity=Decimal('4.00'),
            status='Pending Review',
        )

        self.client.force_authenticate(user=self.owner)
        res_all = self.client.get('/api/inventory/stock/?branch=all')
        self.assertEqual(res_all.status_code, 200)
        actions_by_id = {a['id']: a for a in res_all.data['prescriptive_actions']}
        self.assertEqual(actions_by_id[po_hub_prod.prescriptive_output_ID]['directive_category'], 'produce')
        self.assertEqual(actions_by_id[po_hub_prod.prescriptive_output_ID]['directive_badge'], 'Kitchen Production')
        self.assertEqual(actions_by_id[po_sat_prod.prescriptive_output_ID]['directive_category'], 'dispatch')
        self.assertEqual(actions_by_id[po_sat_prod.prescriptive_output_ID]['directive_badge'], 'Branch Dispatch')

        # Satellite view remains strictly isolated to satellite branch prescriptions
        self.client.force_authenticate(user=self.manager)
        res_sat_only = self.client.get(f'/api/inventory/stock/?branch={self.branch.branch_ID}')
        self.assertEqual(res_sat_only.status_code, 200)
        sat_ids = {a['id'] for a in res_sat_only.data['prescriptive_actions']}
        self.assertIn(po_sat_prod.prescriptive_output_ID, sat_ids)
        self.assertNotIn(po_hub_prod.prescriptive_output_ID, sat_ids)



