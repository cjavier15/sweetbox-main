from django.contrib import admin
from .models import ProductCategory, Product, Transaction, TransactionItem, PaymentRecord

admin.site.register(ProductCategory)
admin.site.register(Product)
admin.site.register(Transaction)
admin.site.register(TransactionItem)
admin.site.register(PaymentRecord)