from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from analytics.views import EnterpriseDashboardView
from django.views.generic.base import RedirectView, TemplateView
from accounts.views import (
    LoginInitiateView,
    LoginVerifyView,
    AdminPanelDataView,
    AdminUserManageView,
    AdminBranchManageView,
    AdminArchiveManageView
)

urlpatterns = [
    path('admin/', admin.site.urls),

    path('login/', TemplateView.as_view(template_name='login.html'), name='login'),
    
    # Auth Endpoints
    path('api/auth/initiate/', LoginInitiateView.as_view(), name='login_initiate'),
    path('api/auth/verify/', LoginVerifyView.as_view(), name='login_verify'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Admin Panel Endpoints
    path('api/accounts/admin/data/', AdminPanelDataView.as_view(), name='admin_panel_data_api'),
    path('api/accounts/admin/users/', AdminUserManageView.as_view(), name='admin_user_manage_api'),
    path('api/accounts/admin/branches/', AdminBranchManageView.as_view(), name='admin_branch_manage_api'),
    path('api/accounts/admin/archives/', AdminArchiveManageView.as_view(), name='admin_archive_manage_api'),

    # API Endpoints
    path('api/pos/', include('pos.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/inventory/', include('inventory.urls')),

    # Frontend Templates
    path('pos/', TemplateView.as_view(template_name='pos.html'), name='pos_frontend'),
    path('analytics/', TemplateView.as_view(template_name='analytics.html'), name='analytics_frontend'),
    path('scm/', TemplateView.as_view(template_name='scm.html'), name='scm_frontend'),
    path('admin-panel/', TemplateView.as_view(template_name='admin_panel.html'), name='admin_panel_frontend'),

    path('enterprise/', EnterpriseDashboardView.as_view(), name='enterprise-dashboard'),

    path('', RedirectView.as_view(url='/login/', permanent=False), name='index'),
]
