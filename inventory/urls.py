from django.urls import path
from .views import LiveStockView, BOMCreateView, ProductDeleteView, ProduceProductView, ManualStockAdjustmentView, SubmitRestockView, ProcessRestockView

urlpatterns = [
    path('stock/', LiveStockView.as_view(), name='live_stock_api'),
    path('bom/create/', BOMCreateView.as_view(), name='bom_create_api'),
    path('bom/delete/<int:product_id>/', ProductDeleteView.as_view(), name='bom_delete_api'),
    path('produce/', ProduceProductView.as_view(), name='produce_product_api'),
    path('adjust/', ManualStockAdjustmentView.as_view(), name='stock_adjust_api'),
    path('restock/submit/', SubmitRestockView.as_view(), name='restock_submit_api'),
    path('restock/process/<int:restock_id>/', ProcessRestockView.as_view(), name='restock_process_api'),
]