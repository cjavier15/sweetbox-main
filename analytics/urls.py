from django.urls import path
from .views import RestockDirectiveView,SalesChatbotView, EnterpriseDashboardDataView, EnterpriseDashboardView, CurrentUserView, ProcessPrescriptionView, ExternalVariableView, RunETLPipelineView, ExportKPIReportView

# Note the exact spelling of urlpatterns here:
urlpatterns = [
    path('restock-directive/', RestockDirectiveView.as_view(), name='restock-directive'),
    path('chat/', SalesChatbotView.as_view(), name='sales-chat'),
    path('dashboard-data/', EnterpriseDashboardDataView.as_view(), name='dashboard-data'),
    path('dashboard/', EnterpriseDashboardView.as_view(), name='enterprise-dashboard'),
    path('current-user/', CurrentUserView.as_view(), name='current-user'),
    path('process-prescription/<int:output_id>/', ProcessPrescriptionView.as_view(), name='process-prescription'),
    path('external-variables/', ExternalVariableView.as_view(), name='external-variables'),
    path('external-variables/<int:var_id>/', ExternalVariableView.as_view(), name='external-variables-delete'),
    path('etl/run/', RunETLPipelineView.as_view(), name='etl-run'),
    path('etl/export/', ExportKPIReportView.as_view(), name='etl-export'),
]