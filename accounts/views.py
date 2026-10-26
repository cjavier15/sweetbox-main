import csv
import json
import jwt
import random
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import authenticate
from django.core.mail import EmailMessage
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTPRecord, AuditLog, Branch
from inventory.models import ProductStock, StockAdjustment
from analytics.models import ArchiveStorage
from pos.models import Transaction, TransactionItem


def log_audit(user, action, module, details):
    AuditLog.objects.create(user=user, action=action, module=module, details=details)


def _is_admin_or_owner(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    role = getattr(user, 'role', '')
    return role in ['Admin', 'System Administrator', 'Business Owner']


class LoginInitiateView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        trusted_token = request.data.get('trusted_device_token')
        
        user = authenticate(email=email, password=password)
        
        if user is not None:
            # 1. Check for valid Trusted Device Token
            if trusted_token:
                try:
                    payload = jwt.decode(trusted_token, settings.SECRET_KEY, algorithms=['HS256'])
                    if payload.get('user_id') == user.user_ID:
                        refresh = RefreshToken.for_user(user)
                        log_audit(user, "Trusted Login", "Authentication", "User logged in via trusted device bypass.")
                        return Response({
                            "status": "trusted_bypass",
                            "access": str(refresh.access_token),
                            "refresh": str(refresh)
                        }, status=status.HTTP_200_OK)
                except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                    pass # Token invalid/expired, fall back to standard OTP flow

            # 2. Generate 6-digit OTP
            otp_code = str(random.randint(100000, 999999))
            OTPRecord.objects.filter(user=user, is_used=False).update(is_used=True)
            
            expiry = timezone.now() + timezone.timedelta(minutes=10)
            OTPRecord.objects.create(user=user, otp_code=otp_code, expiration_time=expiry)
            
            email_msg = EmailMessage(
                subject='Sweet Box Authentication Code',
                body=f'Hello {user.name},\n\nYour 2FA verification code is: {otp_code}\n\nThis code expires in 10 minutes.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email]
            )
            email_msg.send(fail_silently=False)
            
            log_audit(user, "Login Attempt", "Authentication", f"OTP generated and sent to {email}.")
            return Response({"status": "otp_sent", "email": email}, status=status.HTTP_200_OK)
            
        return Response({"error": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)


class LoginVerifyView(APIView):
    permission_classes = []

    def post(self, request):
        email = request.data.get('email')
        otp_code = request.data.get('otp')
        
        try:
            user = User.objects.get(email=email)
            record = OTPRecord.objects.filter(
                user=user, otp_code=otp_code, is_used=False, expiration_time__gt=timezone.now()
            ).first()
            
            if record:
                record.is_used = True
                record.save()
                
                refresh = RefreshToken.for_user(user)
                
                # Generate the 7-Day Trusted Device Token
                trusted_payload = {
                    'user_id': user.user_ID,
                    'exp': int((timezone.now() + timezone.timedelta(days=7)).timestamp())
                }
                trusted_token = jwt.encode(trusted_payload, settings.SECRET_KEY, algorithm='HS256')
                
                log_audit(user, "Successful Login", "Authentication", "User verified OTP and accessed the system.")
                
                return Response({
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'trusted_device_token': trusted_token
                }, status=status.HTTP_200_OK)
                
            return Response({"error": "Invalid or expired OTP code."}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({"error": "User record not found."}, status=status.HTTP_404_NOT_FOUND)


class AdminPanelDataView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_admin_or_owner(request.user):
            return Response({"error": "Unauthorized. Requires Admin or Business Owner access."}, status=status.HTTP_403_FORBIDDEN)

        # 1. Users List (0 N+1 queries via select_related)
        users = list(User.objects.select_related('branch').order_by('user_ID'))
        users_data = [
            {
                "user_ID": u.user_ID,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "branch_id": u.branch_id,
                "branch_name": u.branch.name if u.branch else "All Branches (HQ)",
                "is_active": u.is_active,
                "create_date": u.create_date.strftime("%Y-%m-%d") if u.create_date else ""
            }
            for u in users
        ]

        # 2. Branches List (0 N+1 queries via pre-aggregated counts)
        branches = list(Branch.objects.order_by('branch_ID'))
        staff_counts = {
            row['branch_id']: row['c']
            for row in User.objects.values('branch_id').annotate(c=Count('user_ID'))
            if row['branch_id'] is not None
        }
        product_counts = {
            row['branch_id']: row['c']
            for row in ProductStock.objects.values('branch_id').annotate(c=Count('product_inventory_ID'))
            if row['branch_id'] is not None
        }

        manager_map = {}
        for u in users:
            if u.branch_id and (u.role == 'Branch Manager' or (u.role and 'Manager' in u.role)):
                manager_map[u.branch_id] = u.name

        branches_data = [
            {
                "branch_ID": b.branch_ID,
                "name": b.name,
                "address": b.address,
                "main_hub": bool(b.main_hub or 'ibaan' in b.name.lower()),
                "manager_name": manager_map.get(b.branch_ID, "Unassigned"),
                "staff_count": staff_counts.get(b.branch_ID, 0),
                "product_count": product_counts.get(b.branch_ID, 0),
                "is_online": cache.get(f"branch_online_{b.branch_ID}", True)
            }
            for b in branches
        ]

        # 3. Archive Summary & Recent Archives
        arc_counts = {
            row['module_table']: row['count']
            for row in ArchiveStorage.objects.values('module_table').annotate(count=Count('archive_ID'))
        }
        recent_archives_qs = ArchiveStorage.objects.order_by('-archived_time')[:25]
        recent_archives = [
            {
                "archive_ID": arc.archive_ID,
                "module_table": arc.module_table,
                "record_ID": arc.record_ID,
                "archived_time": arc.archived_time.strftime("%Y-%m-%d %I:%M %p") if arc.archived_time else "",
                "archived_data": arc.archived_data[:250] if arc.archived_data else ""
            }
            for arc in recent_archives_qs
        ]

        # 4. Audit Logs (0 N+1 queries via select_related)
        audit_logs_qs = AuditLog.objects.select_related('user', 'user__branch').order_by('-action_time')[:100]

        def get_badge_type(action):
            if not action:
                return 'action'
            act_lower = action.lower()
            if 'login' in act_lower or 'auth' in act_lower:
                return 'auth'
            if 'export' in act_lower:
                return 'export'
            if any(k in act_lower for k in ['delete', 'refund', 'reject', 'unassign', 'deactivat']):
                return 'delete'
            if any(k in act_lower for k in ['added', 'created', 'configured', 'produced', 'provision']):
                return 'create'
            if any(k in act_lower for k in ['update', 'change', 'edit', 'toggle']):
                return 'update'
            return 'action'

        audit_logs_data = [
            {
                "id": log.audit_ID,
                "user_name": log.user.name if log.user else "System",
                "user_role": log.user.role if log.user else "System",
                "branch": log.user.branch.name if (log.user and log.user.branch) else "All Branches (HQ)",
                "action": log.action,
                "module": log.module,
                "details": log.details,
                "timestamp": log.action_time.strftime('%Y-%m-%d %I:%M %p') if log.action_time else "",
                "badge_type": get_badge_type(log.action)
            }
            for log in audit_logs_qs
        ]

        return Response({
            "users": users_data,
            "branches": branches_data,
            "archives": {
                "transactions_archived": arc_counts.get('TRANSACTIONS', 0),
                "inventory_logs_archived": arc_counts.get('STOCK_ADJUSTMENTS', 0),
                "activity_logs_archived": arc_counts.get('AUDIT_LOGS', 0),
                "users_archived": arc_counts.get('USERS', 0),
                "total_archived": sum(arc_counts.values()),
                "recent": recent_archives
            },
            "audit_logs": audit_logs_data,
            "current_user_id": request.user.user_ID
        }, status=status.HTTP_200_OK)


class AdminUserManageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _is_admin_or_owner(request.user):
            return Response({"error": "Unauthorized access."}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get('action')

        if action == 'create':
            name = request.data.get('name', '').strip()
            email = request.data.get('email', '').strip().lower()
            password = request.data.get('password', '')
            role = request.data.get('role', 'Staff')
            branch_id = request.data.get('branch_id')
            is_active = request.data.get('is_active', True)

            if not name or not email or not password:
                return Response({"error": "Name, email, and password are required."}, status=status.HTTP_400_BAD_REQUEST)
            if len(password) < 6:
                return Response({"error": "Password must be at least 6 characters."}, status=status.HTTP_400_BAD_REQUEST)
            if User.objects.filter(email=email).exists():
                return Response({"error": "Email is already registered."}, status=status.HTTP_400_BAD_REQUEST)

            branch = None
            if branch_id:
                try:
                    branch = Branch.objects.get(pk=branch_id)
                except Branch.DoesNotExist:
                    pass

            is_staff = role in ['Admin', 'System Administrator', 'Business Owner']
            new_user = User.objects.create_user(
                email=email,
                password=password,
                name=name,
                role=role,
                branch=branch,
                is_active=bool(is_active),
                is_staff=is_staff
            )

            log_audit(
                request.user,
                "Created User Account",
                "System Admin",
                f"Created account for {name} ({email}) with role '{role}' assigned to {branch.name if branch else 'HQ'}."
            )
            return Response({
                "status": "success",
                "message": "User account created successfully.",
                "user_id": new_user.user_ID
            }, status=status.HTTP_201_CREATED)

        elif action == 'update':
            user_id = request.data.get('user_id')
            try:
                target_user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            name = request.data.get('name', '').strip()
            email = request.data.get('email', '').strip().lower()
            role = request.data.get('role')
            branch_id = request.data.get('branch_id')
            is_active = request.data.get('is_active')
            password = request.data.get('password')

            if target_user.user_ID == request.user.user_ID and is_active is False:
                return Response({"error": "You cannot deactivate your own logged-in account."}, status=status.HTTP_400_BAD_REQUEST)

            if email and email != target_user.email:
                if User.objects.filter(email=email).exclude(pk=target_user.pk).exists():
                    return Response({"error": "Email is already in use by another user."}, status=status.HTTP_400_BAD_REQUEST)
                target_user.email = email

            if name:
                target_user.name = name
            if role:
                target_user.role = role
                target_user.is_staff = role in ['Admin', 'System Administrator', 'Business Owner']

            if branch_id is not None:
                if branch_id == "" or branch_id is False:
                    target_user.branch = None
                else:
                    try:
                        target_user.branch = Branch.objects.get(pk=branch_id)
                    except Branch.DoesNotExist:
                        target_user.branch = None

            if is_active is not None:
                target_user.is_active = bool(is_active)

            if password and len(password) >= 6:
                target_user.set_password(password)

            target_user.save()
            log_audit(
                request.user,
                "Updated User Account",
                "System Admin",
                f"Updated user account for {target_user.name} ({target_user.email})."
            )
            return Response({"status": "success", "message": "User account updated successfully."}, status=status.HTTP_200_OK)

        elif action in ['toggle_active', 'delete']:
            user_id = request.data.get('user_id')
            try:
                target_user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            if target_user.user_ID == request.user.user_ID:
                return Response({"error": "You cannot modify or delete your own logged-in account."}, status=status.HTTP_400_BAD_REQUEST)

            if action == 'toggle_active':
                target_user.is_active = not target_user.is_active
                target_user.save()
                status_str = "Activated" if target_user.is_active else "Deactivated"
                log_audit(
                    request.user,
                    f"{status_str} User Account",
                    "System Admin",
                    f"{status_str} user account {target_user.name} ({target_user.email})."
                )
                return Response({
                    "status": "success",
                    "is_active": target_user.is_active,
                    "message": f"User account {status_str.lower()} successfully."
                }, status=status.HTTP_200_OK)

            elif action == 'delete':
                u_name = target_user.name
                u_email = target_user.email
                target_user.delete()
                log_audit(
                    request.user,
                    "Deleted User Account",
                    "System Admin",
                    f"Deleted user account {u_name} ({u_email})."
                )
                return Response({"status": "success", "message": "User account deleted successfully."}, status=status.HTTP_200_OK)

        return Response({"error": "Invalid action specified."}, status=status.HTTP_400_BAD_REQUEST)


class AdminBranchManageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _is_admin_or_owner(request.user):
            return Response({"error": "Unauthorized access."}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get('action')
        branch_id = request.data.get('branch_id')

        try:
            branch = Branch.objects.get(pk=branch_id)
        except Branch.DoesNotExist:
            return Response({"error": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)

        if action == 'toggle_status':
            current_status = cache.get(f"branch_online_{branch.branch_ID}", True)
            if 'is_online' in request.data:
                new_status = bool(request.data.get('is_online'))
            else:
                new_status = not current_status

            cache.set(f"branch_online_{branch.branch_ID}", new_status, timeout=None)
            status_label = "Online" if new_status else "Offline"
            log_audit(
                request.user,
                "Changed Branch Status",
                "System Admin",
                f"Changed branch '{branch.name}' status to {status_label}."
            )
            return Response({
                "status": "success",
                "branch_id": branch.branch_ID,
                "is_online": new_status,
                "message": f"{branch.name} is now {status_label}."
            }, status=status.HTTP_200_OK)

        elif action == 'update':
            branch.name = request.data.get('name', branch.name).strip()
            branch.address = request.data.get('address', branch.address).strip()
            branch.save()

            manager_user_id = request.data.get('manager_user_id')
            if manager_user_id:
                try:
                    manager_user = User.objects.get(pk=manager_user_id)
                    manager_user.branch = branch
                    manager_user.role = 'Branch Manager'
                    manager_user.save()
                except User.DoesNotExist:
                    pass

            log_audit(
                request.user,
                "Updated Branch Settings",
                "System Admin",
                f"Updated branch profile and settings for '{branch.name}'."
            )
            return Response({
                "status": "success",
                "message": f"Branch '{branch.name}' updated successfully."
            }, status=status.HTTP_200_OK)

        return Response({"error": "Invalid action specified."}, status=status.HTTP_400_BAD_REQUEST)


class AdminArchiveManageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_admin_or_owner(request.user):
            return Response({"error": "Unauthorized access."}, status=status.HTTP_403_FORBIDDEN)

        mode = request.query_params.get('mode', 'preview')

        if mode == 'export':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="SweetBox_Archive_Export.csv"'
            writer = csv.writer(response)
            writer.writerow(['Archive ID', 'Module / Table', 'Record ID', 'Archived Time', 'Archived Data (JSON)'])
            for arc in ArchiveStorage.objects.order_by('-archived_time'):
                writer.writerow([
                    arc.archive_ID,
                    arc.module_table,
                    arc.record_ID,
                    arc.archived_time.strftime('%Y-%m-%d %H:%M:%S') if arc.archived_time else '',
                    arc.archived_data
                ])
            log_audit(request.user, "Exported Archive", "System Admin", "Exported historical archive storage data to CSV.")
            return response

        # Preview mode
        archive_type = request.query_params.get('archive_type', 'TRANSACTIONS')
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        count = 0
        if archive_type == 'TRANSACTIONS':
            qs = Transaction.objects.all()
            if from_date:
                qs = qs.filter(transaction_date__date__gte=from_date)
            if to_date:
                qs = qs.filter(transaction_date__date__lte=to_date)
            count = qs.count()

        elif archive_type == 'STOCK_ADJUSTMENTS':
            qs = StockAdjustment.objects.all()
            if from_date:
                qs = qs.filter(latest_update__date__gte=from_date)
            if to_date:
                qs = qs.filter(latest_update__date__lte=to_date)
            count = qs.count()

        elif archive_type == 'AUDIT_LOGS':
            qs = AuditLog.objects.exclude(module='System Admin')
            if from_date:
                qs = qs.filter(action_time__date__gte=from_date)
            if to_date:
                qs = qs.filter(action_time__date__lte=to_date)
            count = qs.count()

        elif archive_type == 'USERS':
            qs = User.objects.filter(is_active=False)
            if from_date:
                qs = qs.filter(create_date__date__gte=from_date)
            if to_date:
                qs = qs.filter(create_date__date__lte=to_date)
            count = qs.count()

        return Response({"preview_count": count}, status=status.HTTP_200_OK)

    def post(self, request):
        if not _is_admin_or_owner(request.user):
            return Response({"error": "Unauthorized access."}, status=status.HTTP_403_FORBIDDEN)

        archive_type = request.data.get('archive_type', 'TRANSACTIONS')
        from_date = request.data.get('from_date')
        to_date = request.data.get('to_date')
        keep_active = request.data.get('keep_active', False)

        archived_count = 0

        if archive_type == 'TRANSACTIONS':
            qs = Transaction.objects.prefetch_related('items').all()
            if from_date:
                qs = qs.filter(transaction_date__date__gte=from_date)
            if to_date:
                qs = qs.filter(transaction_date__date__lte=to_date)

            archived_objects = []
            ids_to_delete = []
            for tx in qs:
                items_data = [
                    {
                        "item_id": it.item_ID,
                        "product_id": it.product_id,
                        "quantity": it.quantity,
                        "unit_price": str(it.unit_price),
                        "subtotal": str(it.subtotal)
                    }
                    for it in tx.items.all()
                ]
                data_dict = {
                    "transaction_id": tx.transaction_ID,
                    "branch_id": tx.branch_id,
                    "user_id": tx.user_id,
                    "subtotal_amount": str(tx.subtotal_amount),
                    "discount_type": tx.discount_type,
                    "discount_amount": str(tx.discount_amount),
                    "total_amount": str(tx.total_amount),
                    "transaction_status": tx.transaction_status,
                    "transaction_date": tx.transaction_date.isoformat(),
                    "items": items_data
                }
                archived_objects.append(ArchiveStorage(
                    module_table='TRANSACTIONS',
                    record_ID=tx.transaction_ID,
                    archived_data=json.dumps(data_dict, cls=DjangoJSONEncoder)
                ))
                ids_to_delete.append(tx.transaction_ID)

            ArchiveStorage.objects.bulk_create(archived_objects)
            if not keep_active and ids_to_delete:
                Transaction.objects.filter(transaction_ID__in=ids_to_delete).delete()
            archived_count = len(archived_objects)

        elif archive_type == 'STOCK_ADJUSTMENTS':
            qs = StockAdjustment.objects.all()
            if from_date:
                qs = qs.filter(latest_update__date__gte=from_date)
            if to_date:
                qs = qs.filter(latest_update__date__lte=to_date)

            archived_objects = []
            ids_to_delete = []
            for adj in qs:
                data_dict = {
                    "adjustments_ID": adj.adjustments_ID,
                    "user_id": adj.user_id,
                    "product_inventory_id": adj.product_inventory_id,
                    "ingredients_inventory_id": adj.ingredients_inventory_id,
                    "adjustment_type": adj.adjustment_type,
                    "quantity_change": str(adj.quantity_change),
                    "reason": adj.reason,
                    "latest_update": adj.latest_update.isoformat()
                }
                archived_objects.append(ArchiveStorage(
                    module_table='STOCK_ADJUSTMENTS',
                    record_ID=adj.adjustments_ID,
                    archived_data=json.dumps(data_dict, cls=DjangoJSONEncoder)
                ))
                ids_to_delete.append(adj.adjustments_ID)

            ArchiveStorage.objects.bulk_create(archived_objects)
            if not keep_active and ids_to_delete:
                StockAdjustment.objects.filter(adjustments_ID__in=ids_to_delete).delete()
            archived_count = len(archived_objects)

        elif archive_type == 'AUDIT_LOGS':
            qs = AuditLog.objects.exclude(module='System Admin')
            if from_date:
                qs = qs.filter(action_time__date__gte=from_date)
            if to_date:
                qs = qs.filter(action_time__date__lte=to_date)

            archived_objects = []
            ids_to_delete = []
            for l in qs:
                data_dict = {
                    "audit_ID": l.audit_ID,
                    "user_id": l.user_id,
                    "action": l.action,
                    "module": l.module,
                    "details": l.details,
                    "action_time": l.action_time.isoformat()
                }
                archived_objects.append(ArchiveStorage(
                    module_table='AUDIT_LOGS',
                    record_ID=l.audit_ID,
                    archived_data=json.dumps(data_dict, cls=DjangoJSONEncoder)
                ))
                ids_to_delete.append(l.audit_ID)

            ArchiveStorage.objects.bulk_create(archived_objects)
            if not keep_active and ids_to_delete:
                AuditLog.objects.filter(audit_ID__in=ids_to_delete).delete()
            archived_count = len(archived_objects)

        elif archive_type == 'USERS':
            qs = User.objects.filter(is_active=False)
            if from_date:
                qs = qs.filter(create_date__date__gte=from_date)
            if to_date:
                qs = qs.filter(create_date__date__lte=to_date)

            archived_objects = []
            for u in qs:
                data_dict = {
                    "user_ID": u.user_ID,
                    "branch_id": u.branch_id,
                    "name": u.name,
                    "email": u.email,
                    "role": u.role,
                    "create_date": u.create_date.isoformat() if u.create_date else "",
                    "is_active": u.is_active
                }
                archived_objects.append(ArchiveStorage(
                    module_table='USERS',
                    record_ID=u.user_ID,
                    archived_data=json.dumps(data_dict, cls=DjangoJSONEncoder)
                ))
            ArchiveStorage.objects.bulk_create(archived_objects)
            archived_count = len(archived_objects)

        log_audit(
            request.user,
            "Data Archival Executed",
            "System Admin",
            f"Archived {archived_count} records from {archive_type} into permanent archive storage."
        )

        return Response({
            "status": "success",
            "archived_count": archived_count,
            "message": f"Successfully archived {archived_count} records."
        }, status=status.HTTP_200_OK)
