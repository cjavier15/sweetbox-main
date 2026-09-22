from django.urls import path
from .views import ProductListView, TransactionListView, TransactionCreateView, TransactionRefundView

urlpatterns = [
    path('products/', ProductListView.as_view(), name='product-list'),
    path('transactions/', TransactionListView.as_view(), name='transaction-list'),
    path('checkout/', TransactionCreateView.as_view(), name='checkout'),
    path('refund/<int:txn_id>/', TransactionRefundView.as_view(), name='refund'),
]