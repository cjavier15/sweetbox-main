from django.urls import path
from .views import (
    LiveStockView, 
    IngredientCreateView,
    BOMCreateView, 
    BOMUpdateView,
    ProductDeleteView, 
    ProduceProductView, 
    ManualStockAdjustmentView, 
    SubmitRestockView, 
    ProcessRestockView,
    ProductTransferView,
    CategoryListView,
    BranchProductAssignmentView
)

urlpatterns = [
    path('stock/', LiveStockView.as_view(), name='live_stock_api'),
    path('categories/', CategoryListView.as_view(), name='category_list_api'),
    path('ingredient/add/', IngredientCreateView.as_view(), name='ingredient_add_api'),
    path('bom/create/', BOMCreateView.as_view(), name='bom_create_api'),
    path('bom/update/<int:product_id>/', BOMUpdateView.as_view(), name='bom_update_api'),
    path('bom/delete/<int:product_id>/', ProductDeleteView.as_view(), name='bom_delete_api'),
    path('produce/', ProduceProductView.as_view(), name='produce_product_api'),
    path('transfer/', ProductTransferView.as_view(), name='product_transfer_api'),
    path('branch-assignment/', BranchProductAssignmentView.as_view(), name='branch_product_assignment_api'),
    path('adjust/', ManualStockAdjustmentView.as_view(), name='stock_adjust_api'),
    path('restock/submit/', SubmitRestockView.as_view(), name='restock_submit_api'),
    path('restock/process/<int:restock_id>/', ProcessRestockView.as_view(), name='restock_process_api'),
]