from django.db import models
from django.conf import settings

class ProductCategory(models.Model):
    category_ID = models.AutoField(primary_key=True)
    category_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.category_name

    class Meta:
        verbose_name_plural = "Product Categories"

class Product(models.Model):
    product_ID = models.AutoField(primary_key=True)
    category = models.ForeignKey(ProductCategory, related_name='products', on_delete=models.CASCADE)
    product_name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.product_name

class Transaction(models.Model):
    transaction_ID = models.AutoField(primary_key=True)
    # Use PROTECT so deleting a branch does not delete historical sales data
    branch = models.ForeignKey('accounts.Branch', on_delete=models.PROTECT)
    # Use SET_NULL so if an employee is deleted, the transaction remains but the user becomes null
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discount_type = models.CharField(max_length=50, blank=True, null=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_status = models.CharField(max_length=50) # e.g., 'Completed', 'Voided', 'Refunded'
    transaction_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"TXN-{self.transaction_ID} | {self.transaction_status}"

class TransactionItem(models.Model):
    item_ID = models.AutoField(primary_key=True)
    # CASCADE ensures if a transaction is deleted, its individual items are also wiped
    transaction = models.ForeignKey(Transaction, related_name='items', on_delete=models.CASCADE)
    # PROTECT ensures you cannot delete a product from the database if it has been sold before
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.product_name} (TXN-{self.transaction.transaction_ID})"

class PaymentRecord(models.Model):
    payment_ID = models.AutoField(primary_key=True)
    transaction = models.ForeignKey(Transaction, related_name='payments', on_delete=models.CASCADE)
    
    # Unique constraint ensures the same GCash/Maya reference number isn't reused
    reference_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50) # e.g., 'Cash', 'GCash', 'Split Payment'
    payment_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.payment_ID} - {self.payment_method}"