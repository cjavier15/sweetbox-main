from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from accounts.models import User, Branch, OTPRecord, AuditLog

class AccountsSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Test Branch", address="123 Test St")
        self.owner = User.objects.create_user(
            name="Test Owner",
            email="owner_test@sweetbox.ph",
            password="TestPassword123!",
            role="Business Owner",
            is_active=True
        )
        self.staff = User.objects.create_user(
            name="Test Staff",
            email="staff_test@sweetbox.ph",
            password="TestPassword123!",
            role="Staff",
            branch=self.branch,
            is_active=True
        )

    def test_otp_record_collision_resilience(self):
        """Verify that multiple OTP records can share the same code without IntegrityError (unique=True removed)."""
        code = "123456"
        otp1 = OTPRecord.objects.create(user=self.owner, otp_code=code, expiration_time=timezone.now() + timedelta(minutes=10))
        otp2 = OTPRecord.objects.create(user=self.staff, otp_code=code, expiration_time=timezone.now() + timedelta(minutes=10))
        self.assertEqual(otp1.otp_code, otp2.otp_code)
        self.assertEqual(OTPRecord.objects.filter(otp_code=code).count(), 2)

    def test_login_initiate_success(self):
        payload = {'email': 'owner_test@sweetbox.ph', 'password': 'TestPassword123!'}
        response = self.client.post('/api/auth/initiate/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(OTPRecord.objects.filter(user=self.owner).exists())

    def test_login_initiate_inactive_user(self):
        self.owner.is_active = False
        self.owner.save()
        payload = {'email': 'owner_test@sweetbox.ph', 'password': 'TestPassword123!'}
        response = self.client.post('/api/auth/initiate/', payload, format='json')
        self.assertEqual(response.status_code, 401)

    def test_login_initiate_invalid_email(self):
        payload = {'email': 'nonexistent@sweetbox.ph', 'password': 'WrongPassword'}
        response = self.client.post('/api/auth/initiate/', payload, format='json')
        self.assertEqual(response.status_code, 401)

    def test_login_verify_success(self):
        otp = OTPRecord.objects.create(user=self.owner, otp_code="654321", expiration_time=timezone.now() + timedelta(minutes=10))
        response = self.client.post('/api/auth/verify/', {'email': 'owner_test@sweetbox.ph', 'otp': '654321'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_verify_expired_otp(self):
        otp = OTPRecord.objects.create(user=self.owner, otp_code="999999", expiration_time=timezone.now() - timedelta(minutes=5))
        response = self.client.post('/api/auth/verify/', {'email': 'owner_test@sweetbox.ph', 'otp': '999999'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('expired', response.data.get('error', '').lower())

    def test_current_user_profile(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/analytics/current-user/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], 'owner_test@sweetbox.ph')
        self.assertEqual(response.data['role'], 'Business Owner')



class AdminPanelApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.hub = Branch.objects.create(name="Sweet Box - Ibaan", address="Ibaan Main", main_hub=True)
        self.sat = Branch.objects.create(name="Sweet Box - Lipa", address="Lipa Satellite", main_hub=False)
        self.owner = User.objects.create_user(
            name="Admin Owner",
            email="admin_owner@sweetbox.ph",
            password="Password123!",
            role="Business Owner",
            is_active=True
        )
        self.admin = User.objects.create_user(
            name="Sys Admin",
            email="sys_admin@sweetbox.ph",
            password="Password123!",
            role="System Administrator",
            is_active=True
        )
        self.staff = User.objects.create_user(
            name="Cashier Staff",
            email="cashier_staff@sweetbox.ph",
            password="Password123!",
            role="Staff",
            branch=self.sat,
            is_active=True
        )

    def test_admin_panel_data_unauthorized_for_staff(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/accounts/admin/data/')
        self.assertEqual(res.status_code, 403)

    def test_admin_panel_data_success_for_owner(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get('/api/accounts/admin/data/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('users', res.data)
        self.assertIn('branches', res.data)
        self.assertIn('archives', res.data)
        self.assertIn('audit_logs', res.data)
        self.assertEqual(len(res.data['branches']), 2)

    def test_admin_user_manage_create_and_update(self):
        self.client.force_authenticate(user=self.owner)
        # Create
        create_payload = {
            'action': 'create',
            'name': 'New Manager',
            'email': 'new_mgr@sweetbox.ph',
            'password': 'Password123!',
            'role': 'Branch Manager',
            'branch_id': self.sat.branch_ID,
            'is_active': True
        }
        res = self.client.post('/api/accounts/admin/users/', create_payload, format='json')
        self.assertEqual(res.status_code, 201)
        new_uid = res.data['user_id']
        self.assertTrue(User.objects.filter(email='new_mgr@sweetbox.ph').exists())

        # Update
        update_payload = {
            'action': 'update',
            'user_id': new_uid,
            'name': 'Updated Manager',
            'email': 'new_mgr@sweetbox.ph',
            'role': 'Branch Manager',
            'branch_id': self.hub.branch_ID,
            'is_active': True
        }
        res = self.client.post('/api/accounts/admin/users/', update_payload, format='json')
        self.assertEqual(res.status_code, 200)
        updated_user = User.objects.get(pk=new_uid)
        self.assertEqual(updated_user.name, 'Updated Manager')
        self.assertEqual(updated_user.branch, self.hub)

        # Toggle Active
        res = self.client.post('/api/accounts/admin/users/', {'action': 'toggle_active', 'user_id': new_uid}, format='json')
        self.assertEqual(res.status_code, 200)
        updated_user.refresh_from_db()
        self.assertFalse(updated_user.is_active)

    def test_admin_branch_manage_toggle_and_update(self):
        self.client.force_authenticate(user=self.admin)
        # Toggle Status
        res = self.client.post('/api/accounts/admin/branches/', {'action': 'toggle_status', 'branch_id': self.sat.branch_ID, 'is_online': False}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['is_online'])

        # Update Branch
        res = self.client.post('/api/accounts/admin/branches/', {
            'action': 'update',
            'branch_id': self.sat.branch_ID,
            'name': 'Sweet Box - Lipa City',
            'address': 'New Address 456'
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.sat.refresh_from_db()
        self.assertEqual(self.sat.name, 'Sweet Box - Lipa City')

    def test_admin_archive_manage_preview_and_export(self):
        self.client.force_authenticate(user=self.owner)
        # Preview
        res = self.client.get('/api/accounts/admin/archives/?mode=preview&archive_type=TRANSACTIONS')
        self.assertEqual(res.status_code, 200)
        self.assertIn('preview_count', res.data)

        # Export CSV
        res = self.client.get('/api/accounts/admin/archives/?mode=export')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'text/csv')


    def test_admin_panel_page_view_unauthenticated_redirect(self):
        res = self.client.get('/admin-panel/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login/', res.url)

    def test_admin_panel_page_view_staff_redirect(self):
        self.client.force_login(self.staff)
        res = self.client.get('/admin-panel/')
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/pos/')

    def test_admin_panel_page_view_owner_redirect(self):
        self.client.force_login(self.owner)
        res = self.client.get('/admin-panel/')
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/enterprise/')

    def test_admin_panel_page_view_admin_success(self):
        self.client.force_login(self.admin)
        res = self.client.get('/admin-panel/')
        self.assertEqual(res.status_code, 200)
