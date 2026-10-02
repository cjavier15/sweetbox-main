from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from accounts.models import User, Branch, OTPRecord

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
