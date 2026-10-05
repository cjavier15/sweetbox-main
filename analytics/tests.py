from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User, Branch
from inventory.models import Ingredient, IngredientStock, ConstraintParameter, BillOfMaterial, ProductStock
from pos.models import Product, ProductCategory, Transaction, TransactionItem, PaymentRecord
from analytics.models import ExternalVariable, KPIRecord, PrescriptiveOutput, ChatbotLog
from analytics.services import _clean_json_text, _generate_rule_based_prescriptions, is_sweetbox_related_query, _get_active_events_context

class AnalyticsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Analytics Branch", address="Analytic Ave")
        self.owner = User.objects.create(name="Owner", email="owner_ana@sweetbox.ph", role="Business Owner", is_active=True)
        self.manager = User.objects.create(name="Manager", email="mgr_ana@sweetbox.ph", role="Branch Manager", branch=self.branch, is_active=True)
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

    def test_chatbot_get_owner_allowed(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/analytics/chat/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('history', res.data)
        self.assertEqual(res.data['user_name'], self.owner.name)
        self.assertEqual(res.data['role'], 'Business Owner')

    def test_chatbot_get_staff_forbidden(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/analytics/chat/')
        self.assertEqual(res.status_code, 403)

    def test_chatbot_get_manager_forbidden(self):
        self.client.force_authenticate(user=self.manager)
        res = self.client.get('/api/analytics/chat/')
        self.assertEqual(res.status_code, 403)

    def test_chatbot_post_owner_allowed_and_logged(self):
        self.client.force_authenticate(user=self.owner)
        payload = {'branch_id': self.branch.branch_ID, 'query': 'What is our top selling product?'}
        res = self.client.post('/api/analytics/chat/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('reply', res.data)
        self.assertTrue(ChatbotLog.objects.filter(user=self.owner, query_text=payload['query']).exists())

    def test_chatbot_post_staff_forbidden(self):
        self.client.force_authenticate(user=self.staff)
        payload = {'branch_id': self.branch.branch_ID, 'query': 'Give me sales info.'}
        res = self.client.post('/api/analytics/chat/', payload, format='json')
        self.assertEqual(res.status_code, 403)

    def test_chatbot_post_manager_forbidden(self):
        self.client.force_authenticate(user=self.manager)
        payload = {'branch_id': self.branch.branch_ID, 'query': 'Give me sales info.'}
        res = self.client.post('/api/analytics/chat/', payload, format='json')
        self.assertEqual(res.status_code, 403)

    def test_chatbot_greeting_response(self):
        self.client.force_authenticate(user=self.owner)
        payload = {'branch_id': self.branch.branch_ID, 'query': 'Hello'}
        res = self.client.post('/api/analytics/chat/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn(f"Hello, {self.owner.name}!", res.data['reply'])
        log = ChatbotLog.objects.filter(user=self.owner, query_text='Hello').first()
        self.assertIsNotNone(log)
        self.assertIn(f"Hello, {self.owner.name}!", log.response_text)

    def test_chatbot_off_topic_guardrail(self):
        self.client.force_authenticate(user=self.owner)
        payload = {'branch_id': self.branch.branch_ID, 'query': 'What is the capital of France?'}
        res = self.client.post('/api/analytics/chat/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Sweet Box', res.data['reply'])
        self.assertIn('cannot assist with topics outside sweet box', res.data['reply'].lower())
        self.assertTrue(ChatbotLog.objects.filter(user=self.owner, query_text=payload['query']).exists())

    def test_prescriptions_realistic_and_measurable(self):
        # Create an active external event
        from django.utils import timezone
        today = timezone.now().date()
        ExternalVariable.objects.create(
            name="Harvest Festival",
            variable_type="Local Event",
            start_date=today,
            end_date=today + timezone.timedelta(days=3),
            impact_level="High",
            is_active=True
        )

        low_stocks = [self.stock]
        result = _generate_rule_based_prescriptions(self.branch, low_stocks)
        self.assertEqual(result['status'], 'generated')
        po = PrescriptiveOutput.objects.get(prescriptive_output_ID=result['outputs'][0])
        
        # Verify recommended quantity respects constraints
        self.assertGreaterEqual(float(po.recommended_quantity), float(self.constraint.min_order_quantity))
        self.assertLessEqual(float(po.recommended_quantity), float(self.constraint.max_order_quantity))
        
        # Verify realistic and measurable description metrics in justification and recommendation
        combined_text = (po.justification + " " + po.recommendation).lower()
        self.assertIn("burn rate", combined_text)
        self.assertIn("runway", combined_text)
        self.assertIn("estimated cost: ₱", combined_text)
        self.assertIn("harvest festival", combined_text)

    def test_restock_directive_single_branch_owner(self):
        self.client.force_authenticate(user=self.owner)
        payload = {'branch_id': self.branch.branch_ID}
        res = self.client.post('/api/analytics/restock-directive/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'generated')
        self.assertIn('outputs', res.data)
        self.assertTrue(len(res.data['outputs']) > 0)

    def test_restock_directive_all_branches_owner(self):
        self.client.force_authenticate(user=self.owner)
        payload = {'branch_id': 'all'}
        res = self.client.post('/api/analytics/restock-directive/', payload, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['status'], 'generated')
        self.assertIn('outputs', res.data)
        self.assertIn('branches_analyzed', res.data)
        self.assertGreaterEqual(res.data['branches_analyzed'], 1)

    def test_restock_directive_non_owner_forbidden_all_or_other_branch(self):
        other_branch = Branch.objects.create(name="Other Branch", address="Other Ave")
        self.client.force_authenticate(user=self.manager)
        # Attempt 'all'
        res_all = self.client.post('/api/analytics/restock-directive/', {'branch_id': 'all'}, format='json')
        self.assertEqual(res_all.status_code, 403)
        # Attempt other branch
        res_other = self.client.post('/api/analytics/restock-directive/', {'branch_id': other_branch.branch_ID}, format='json')
        self.assertEqual(res_other.status_code, 403)

    def test_chatbot_answers_are_dynamic_across_queries(self):
        self.client.force_authenticate(user=self.owner)
        # Top products query
        res_prod = self.client.post('/api/analytics/chat/', {'branch_id': self.branch.branch_ID, 'query': 'What is our top selling product?'}, format='json')
        self.assertEqual(res_prod.status_code, 200)
        # Low stock query
        res_stock = self.client.post('/api/analytics/chat/', {'branch_id': self.branch.branch_ID, 'query': 'What ingredients need to be restocked right now?'}, format='json')
        self.assertEqual(res_stock.status_code, 200)
        # Branch comparison query
        res_branch = self.client.post('/api/analytics/chat/', {'branch_id': self.branch.branch_ID, 'query': 'Compare all branches performance.'}, format='json')
        self.assertEqual(res_branch.status_code, 200)

        # Verify that responses are distinct and not a single static string
        reply_prod = res_prod.data['reply']
        reply_stock = res_stock.data['reply']
        reply_branch = res_branch.data['reply']

        self.assertNotEqual(reply_prod, reply_stock)
        self.assertNotEqual(reply_prod, reply_branch)
        self.assertNotEqual(reply_stock, reply_branch)

    def test_scm_data_includes_branch_in_prescriptive_actions(self):
        # Generate a prescription first
        low_stocks = [self.stock]
        _generate_rule_based_prescriptions(self.branch, low_stocks)

        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/inventory/stock/?branch=all')
        self.assertEqual(res.status_code, 200)
        actions = res.data.get('prescriptive_actions', [])
        self.assertTrue(len(actions) > 0)
        self.assertIn('branch', actions[0])
        self.assertIn('branch_id', actions[0])
        self.assertEqual(actions[0]['branch'], self.branch.name)
        self.assertEqual(actions[0]['branch_id'], self.branch.branch_ID)

