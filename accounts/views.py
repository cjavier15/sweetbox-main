import jwt
import random
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import authenticate
from django.core.mail import EmailMessage
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, OTPRecord, AuditLog

def log_audit(user, action, module, details):
    AuditLog.objects.create(user=user, action=action, module=module, details=details)

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
                from_email='security@sweetbox.ph',
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