from django.contrib import admin
from .models import Branch, User, OTPRecord, AuditLog

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('branch_ID', 'name', 'address', 'main_hub')
    list_filter = ('main_hub',)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('user_ID', 'name', 'email', 'role', 'branch', 'is_active')
    list_filter = ('role', 'branch')
    search_fields = ('name', 'email')

admin.site.register(OTPRecord)
admin.site.register(AuditLog)