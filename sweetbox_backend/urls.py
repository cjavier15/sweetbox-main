from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from analytics.views import EnterpriseDashboardView
from django.views.generic.base import RedirectView, TemplateView
from accounts.views import LoginInitiateView, LoginVerifyView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('login/', TemplateView.as_view(template_name='login.html'), name='login'),
    
    # Auth Endpoints
    path('api/auth/initiate/', LoginInitiateView.as_view(), name='login_initiate'),
    path('api/auth/verify/', LoginVerifyView.as_view(), name='login_verify'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # API Endpoints
    path('api/pos/', include('pos.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/inventory/', include('inventory.urls')),

    # Frontend Templates
    path('pos/', TemplateView.as_view(template_name='pos.html'), name='pos_frontend'),
    path('analytics/', TemplateView.as_view(template_name='analytics.html'), name='analytics_frontend'),
    path('scm/', TemplateView.as_view(template_name='scm.html'), name='scm_frontend'),

    path('enterprise/', EnterpriseDashboardView.as_view(), name='enterprise-dashboard'),
    path('', RedirectView.as_view(url='/enterprise/', permanent=False), name='index'),

    path('', RedirectView.as_view(url='/login/', permanent=False), name='index'),
]