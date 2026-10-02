from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User, Branch, AuditLog
from inventory.models import ProductStock
from pos.models import Product, ProductCategory, Transaction, TransactionItem, PaymentRecord

class POSTransactionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="POS Branch", address="Retail Ave")
        self.owner = User.objects.create(name="Owner", email="owner_pos@sweetbox.ph", role="Business Owner", is_active=True)
        self.staff = User.objects.create(name="Staff", email="staff_pos@sweetbox.ph", role="Staff", branch=self.branch, is_active=True)

        self.category = ProductCategory.objects.create(category_name="Pastries")
        self.product = Product.objects.create(category=self.category, product_name="Croissant", price=120.00, is_active=True)
        self.stock = ProductStock.objects.create(branch=self.branch, product=self.product, quantity_available=20)

    def test_pos_access_restricted_to_staff(self):
        """Business Owner must NOT be able to process transactions via POS checkout."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            'items': [{'product_id': self.product.product_ID, 'quantity': 2, 'unit_price': 120.00}],
            'total_amount': 240.00,
            'payment_method': 'Cash'
        }
        response = self.client.post('/api/pos/checkout/', payload, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertIn("Only Staff can process transactions", response.data.get('error', ''))

    def test_pos_access_allowed_for_staff(self):
        """Staff can successfully process a transaction, deducting finished goods inventory."""
        self.client.force_authenticate(user=self.staff)
        payload = {
            'items': [{'product_id': self.product.product_ID, 'quantity': 3, 'unit_price': 120.00}],
            'total_amount': 360.00,
            'payment_method': 'Cash'
        }
        response = self.client.post('/api/pos/checkout/', payload, format='json')
        self.assertEqual(response.status_code, 201)

        # Inventory deduction
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_available, 17)

        # Transaction created
        txn = Transaction.objects.get(transaction_ID=response.data['transaction_ID'])
        self.assertEqual(txn.transaction_status, 'Completed')
        self.assertEqual(txn.subtotal_amount, Decimal('360.00'))
        self.assertEqual(txn.total_amount, Decimal('360.00'))

    def test_pos_checkout_insufficient_stock(self):
        self.client.force_authenticate(user=self.staff)
        payload = {
            'items': [{'product_id': self.product.product_ID, 'quantity': 50, 'unit_price': 120.00}],
            'total_amount': 6000.00,
            'payment_method': 'Cash'
        }
        response = self.client.post('/api/pos/checkout/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient stock", response.data.get('error', ''))

    def test_transaction_list_staff_vs_owner(self):
        Transaction.objects.create(
            branch=self.branch, user=self.staff, subtotal_amount=Decimal('120.00'),
            total_amount=Decimal('120.00'), transaction_status='Completed'
        )
        # Staff sees transaction
        self.client.force_authenticate(user=self.staff)
        res_staff = self.client.get('/api/pos/transactions/')
        self.assertEqual(len(res_staff.data), 1)

        # Owner cannot access POS transactions (returns empty)
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.get('/api/pos/transactions/')
        self.assertEqual(len(res_owner.data), 0)

    def test_product_list_staff_vs_owner(self):
        # Staff sees products
        self.client.force_authenticate(user=self.staff)
        res_staff = self.client.get('/api/pos/products/')
        self.assertEqual(len(res_staff.data), 1)

        # Owner is blocked from POS product list (returns empty)
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.get('/api/pos/products/')
        self.assertEqual(len(res_owner.data), 0)

    def test_transaction_refund_staff_only_and_restores_stock(self):
        txn = Transaction.objects.create(
            branch=self.branch, user=self.staff, subtotal_amount=Decimal('240.00'),
            total_amount=Decimal('240.00'), transaction_status='Completed'
        )
        TransactionItem.objects.create(
            transaction=txn, product=self.product, quantity=2,
            unit_price=Decimal('120.00'), subtotal=Decimal('240.00')
        )
        self.stock.quantity_available = 10
        self.stock.save()

        # Owner cannot refund (returns 403)
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.delete(f'/api/pos/refund/{txn.transaction_ID}/')
        self.assertEqual(res_owner.status_code, 403)

        # Staff can refund
        self.client.force_authenticate(user=self.staff)
        res_staff = self.client.delete(f'/api/pos/refund/{txn.transaction_ID}/')
        self.assertEqual(res_staff.status_code, 200)

        txn.refresh_from_db()
        self.assertEqual(txn.transaction_status, 'Refunded')

        # Stock rolled back (+2)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity_available, 12)
