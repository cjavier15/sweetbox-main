from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User, Branch
from inventory.models import Ingredient, IngredientStock, ConstraintParameter, BillOfMaterial, ProductStock
from pos.models import Product, ProductCategory, Transaction, TransactionItem, PaymentRecord
from analytics.models import ExternalVariable, KPIRecord, PrescriptiveOutput
from analytics.services import _clean_json_text, _generate_rule_based_prescriptions

class AnalyticsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Analytics Branch", address="Analytic Ave")
        self.owner = User.objects.create(name="Owner", email="owner_ana@sweetbox.ph", role="Business Owner", is_active=True)
        self.staff = User.objects.create(name="Staff", email="staff_ana@sweetbox.ph", role="Staff", branch=self.branch, is_active=True)

        self.category = ProductCategory.objects.create(category_name="Beverages")
        self.product = Product.objects.create(category=self.category, product_name="Iced Coffee", price=150.00, is_active=True)
        self.ingredient = Ingredient.objects.create(ingredient_name="Coffee Beans", measurement_unit="kg", cost_per_unit=Decimal('500.00'))
        self.stock = IngredientStock.objects.create(branch=self.branch, ingredient=self.ingredient, quantity_available=Decimal('2.00'), reorder_threshold=Decimal('5.00'))
        self.constraint = ConstraintParameter.objects.create(branch=self.branch, ingredient=self.ingredient, min_order_quantity=Decimal('5.00'), max_order_quantity=Decimal('20.00'), capacity_limit=Decimal('50.00'), lead_time_days=3)

        self.txn = Transaction.objects.create(
            branch=self.branch, user=self.staff, subtotal_amount=Decimal('300.00'),
            total_amount=Decimal('300.00'), transaction_status='Completed'
        )
        TransactionItem.objects.create(transaction=self.txn, product=self.product, quantity=2, unit_price=Decimal('150.00'), subtotal=Decimal('300.00'))
        PaymentRecord.objects.create(transaction=self.txn, amount_paid=Decimal('300.00'), payment_method='Cash')

    def test_enterprise_dashboard_data_success_for_owner(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/analytics/dashboard-data/?filter=this_month')
        self.assertEqual(response.status_code, 200)
        self.assertIn('scorecards', response.data)
        self.assertIn('time_series', response.data)
        self.assertIn('branch_performance', response.data)
        self.assertIn('top_products', response.data)
        self.assertEqual(response.data['scorecards']['revenue'], 300.0)
        self.assertEqual(response.data['scorecards']['transactions'], 1)

    def test_enterprise_dashboard_data_filters(self):
        self.client.force_authenticate(user=self.owner)
        for f in ['this_week', 'this_month', 'last_7_months']:
            res = self.client.get(f'/api/analytics/dashboard-data/?filter={f}')
            self.assertEqual(res.status_code, 200)

    def test_external_variables_crud(self):
        self.client.force_authenticate(user=self.owner)
        # Create
        payload = {
            'name': 'Town Fiesta',
            'variable_type': 'Local Event',
            'start_date': '2026-10-01',
            'end_date': '2026-10-03',
            'impact_level': 'High'
        }
        res_create = self.client.post('/api/analytics/external-variables/', payload, format='json')
        self.assertEqual(res_create.status_code, 201)
        ev = ExternalVariable.objects.get(name='Town Fiesta')

        # List
        res_list = self.client.get('/api/analytics/external-variables/')
        self.assertEqual(res_list.status_code, 200)
        self.assertTrue(any(v['name'] == 'Town Fiesta' for v in res_list.data))

        # Delete
        res_del = self.client.delete(f'/api/analytics/external-variables/{ev.variable_ID}/')
        self.assertEqual(res_del.status_code, 200)

    def test_run_etl_pipeline_owner_only(self):
        # Staff denied
        self.client.force_authenticate(user=self.staff)
        res_staff = self.client.post('/api/analytics/etl/run/')
        self.assertEqual(res_staff.status_code, 403)

        # Owner allowed
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.post('/api/analytics/etl/run/')
        self.assertEqual(res_owner.status_code, 200)
        self.assertTrue(KPIRecord.objects.filter(branch=self.branch).exists())

    def test_clean_json_text_helper(self):
        raw_markdown = '```json\n[{"ingredient": "Flour", "recommended_qty": 10}]\n```'
        cleaned = _clean_json_text(raw_markdown)
        self.assertEqual(cleaned, '[{"ingredient": "Flour", "recommended_qty": 10}]')

    def test_generate_rule_based_prescriptions(self):
        low_stocks = [self.stock]
        result = _generate_rule_based_prescriptions(self.branch, low_stocks)
        self.assertEqual(result['status'], 'generated')
        self.assertTrue(result['fallback'])
        self.assertEqual(len(result['outputs']), 1)
        po = PrescriptiveOutput.objects.get(prescriptive_output_ID=result['outputs'][0])
        self.assertEqual(po.branch, self.branch)
        self.assertEqual(po.ingredient, self.ingredient)
        self.assertGreaterEqual(float(po.recommended_quantity), 5.0)
