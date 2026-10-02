from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User, Branch, AuditLog
from pos.models import Product, ProductCategory
from inventory.models import (
    Ingredient, IngredientStock, ProductStock, BillOfMaterial, 
    RestockRequest, ProductTransfer, StockAdjustment
)

class InventoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hub = Branch.objects.create(name="Main Hub", address="Hub St", main_hub=True)
        self.branch = Branch.objects.create(name="Branch 1", address="Branch St", main_hub=False)
        self.owner = User.objects.create(name="Owner", email="owner_inv@sweetbox.ph", role="Business Owner", is_active=True)
        self.manager = User.objects.create(name="Manager", email="manager_inv@sweetbox.ph", role="Branch Manager", branch=self.branch, is_active=True)
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

    def test_produce_product_view_satellite_branch_manager(self):
        """Branch manager producing items strictly produces at their branch and deducts branch ingredients."""
        # Setup branch stocks: Flour 50, Sugar 30
        branch_flour = IngredientStock.objects.create(
            branch=self.branch, ingredient=self.flour, quantity_available=Decimal('50.00'), total_cost=Decimal('2500.00')
        )
        branch_sugar = IngredientStock.objects.create(
            branch=self.branch, ingredient=self.sugar, quantity_available=Decimal('30.00'), total_cost=Decimal('1200.00')
        )

        self.client.force_authenticate(user=self.manager)
        # Even if payload erroneously sends branch_id=hub, backend binds strictly to self.branch
        payload = {
            'product_id': self.product.product_ID,
            'quantity': 4,
            'branch_id': self.hub.branch_ID
        }
        response = self.client.post('/api/inventory/produce/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIn("produced 4", response.data.get('message', ''))
        self.assertIn(self.branch.name, response.data.get('message', ''))

        # Branch flour deducted: 50 - (4 * 2) = 42
        branch_flour.refresh_from_db()
        self.assertEqual(branch_flour.quantity_available, Decimal('42.00'))

        # Branch sugar deducted: 30 - (4 * 1) = 26
        branch_sugar.refresh_from_db()
        self.assertEqual(branch_sugar.quantity_available, Decimal('26.00'))

        # Branch product stock increased to 4
        branch_ps = ProductStock.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(branch_ps.quantity_available, Decimal('4.00'))

        # Hub flour was UNTOUCHED (still 100)
        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.quantity_available, Decimal('100.00'))

    def test_produce_product_view_satellite_branch_insufficient(self):
        """Satellite branch fails if its own ingredients are insufficient even if Hub has plenty."""
        # Setup branch with only 1kg flour (needs 2kg per cake)
        IngredientStock.objects.create(
            branch=self.branch, ingredient=self.flour, quantity_available=Decimal('1.00'), total_cost=Decimal('50.00')
        )
        IngredientStock.objects.create(
            branch=self.branch, ingredient=self.sugar, quantity_available=Decimal('10.00'), total_cost=Decimal('400.00')
        )

        self.client.force_authenticate(user=self.manager)
        payload = {
            'product_id': self.product.product_ID,
            'quantity': 2, # needs 4kg flour
        }
        response = self.client.post('/api/inventory/produce/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient Flour at Branch 1", response.data.get('error', ''))

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
            'ingredient_name': 'Flour',
            'quantity': 10,
            'branch_id': self.branch.branch_ID
        }
        response = self.client.post('/api/inventory/restock/submit/', payload, format='json')
        self.assertEqual(response.status_code, 403)

        # Branch Manager should be accepted
        self.client.force_authenticate(user=self.manager)
        response = self.client.post('/api/inventory/restock/submit/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(RestockRequest.objects.filter(ingredient=self.flour, destination_branch=self.branch).exists())

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

        # Check stock initialized at hub with 20, and branch with 0
        hub_stock = IngredientStock.objects.get(branch=self.hub, ingredient=matcha)
        self.assertEqual(hub_stock.quantity_available, Decimal('20.00'))
        branch_stock = IngredientStock.objects.get(branch=self.branch, ingredient=matcha)
        self.assertEqual(branch_stock.quantity_available, Decimal('0.00'))

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
        self.flour_stock.refresh_from_db()
        self.assertEqual(self.flour_stock.quantity_available, Decimal('100.00'))

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
        """Test adjust endpoint dynamically creates stock record if lookup is by branch_id and target_id."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            'item_type': 'ingredient',
            'branch_id': self.branch.branch_ID,
            'target_id': self.sugar.ingredient_ID,
            'adjustment_type': 'Stock-in',
            'quantity_change': 50,
            'reason': 'Direct branch delivery'
        }
        res = self.client.post('/api/inventory/adjust/', payload, format='json')
        self.assertEqual(res.status_code, 200)

        stock = IngredientStock.objects.get(branch=self.branch, ingredient=self.sugar)
        self.assertEqual(stock.quantity_available, Decimal('50.00'))

    def test_branch_stock_visibility_hub_vs_satellite(self):
        """Test that main hub sees all ingredients, while satellite branches only see non-cake/pastry ingredients."""
        coffee_cat = ProductCategory.objects.create(category_name="Coffee")
        coffee_beans = Ingredient.objects.create(
            ingredient_name="Coffee Beans", category=coffee_cat, measurement_unit="kg", cost_per_unit=Decimal('300.00')
        )
        # Create stocks at hub and branch
        IngredientStock.objects.create(branch=self.hub, ingredient=coffee_beans, quantity_available=Decimal('20.00'))
        IngredientStock.objects.create(branch=self.branch, ingredient=coffee_beans, quantity_available=Decimal('10.00'))
        IngredientStock.objects.create(branch=self.branch, ingredient=self.flour, quantity_available=Decimal('15.00'))
        IngredientStock.objects.create(branch=self.branch, ingredient=self.sugar, quantity_available=Decimal('12.00'))

        # Hub Staff / Owner: can see all ingredients (Flour, Sugar, Coffee Beans)
        hub_staff = User.objects.create(name="Hub Staff", email="hubstaff@sweetbox.ph", role="Staff", branch=self.hub, is_active=True)
        self.client.force_authenticate(user=hub_staff)
        res_hub = self.client.get('/api/inventory/stock/')
        self.assertEqual(res_hub.status_code, 200)
        hub_items = [i['ingredient_name'] for i in res_hub.data['inventory']]
        self.assertIn("Flour", hub_items)
        self.assertIn("Sugar", hub_items)
        self.assertIn("Coffee Beans", hub_items)

        # Satellite Branch Staff: MUST ONLY see non-cake/pastry ingredients (Coffee Beans)
        self.client.force_authenticate(user=self.staff)
        res_branch = self.client.get('/api/inventory/stock/')
        self.assertEqual(res_branch.status_code, 200)
        branch_items = [i['ingredient_name'] for i in res_branch.data['inventory']]
        self.assertIn("Coffee Beans", branch_items)
        self.assertNotIn("Flour", branch_items)
        self.assertNotIn("Sugar", branch_items)

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
