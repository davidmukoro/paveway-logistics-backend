from datetime import timezone
from tokenize import TokenError
from urllib import request
from django.shortcuts import render

from .notifications.service import (
    send_notification,
    get_notification_recipients,
    send_bulk_notification,
)
from hmcs.models import AllowanceDeduction
from .models import (
    Bank,
    ExpenseCategory,
    NigState,
    NotificationLog,
    NotificationTemplate,
    NotificationType,
    User,
    Access,
    Auditlog,
    PayIntegration,
    Lga,
    UserSession,
    Zone,
    Pricing,
)
from .serializers import (
    ActiveSessionSerializer,
    AllowanceDeductionSerializer,
    BankSerializer,
    ExpenseCategorySerializer,
    NotificationLogSerializer,
    NotificationTemplateSerializer,
    NotificationTypeSerializer,
    UserSerializer,
    BackendUserSerializer,
    AuditlogSerializer,
    GetStaffList,
    GetCustomerList,
    UpdateUserSerializer,
    ChangePasswordSerializer,
    UpdateProfileSerializer,
    PasswordResetRequestSerializer,
    PasswordResetSerializer,
    AccessSerializer,
    UpdateCreditLimitSerializer,
    StaffSerializer,
    PermissionSerializer,
    NigStateSerializer,
    ZoneSerializer,
    LgaSerializer,
    PricingSerializer,
)
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .permissions import (
    IsSuperAdmin,
    IsMarketer,
    IsAuthenticatedAndStaff,
    IsSuperAdminOrReadOnly,
)
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
import logging
from .utils import AuditedModelViewSet, get_client_ip, log_activity, log_user_activity
from rest_framework.exceptions import NotFound
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt

# from django.contrib.auth import get_user_model
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.response import Response
from django.db.models import OuterRef, Subquery
from django.http import JsonResponse
import requests
from setup.utils import getCloudinaryPath
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework import permissions


# Create your views here.
class CreateUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]  # allow any one without logging
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    # permission_classes =[IsAuthenticated] #They must login to access this


class StaffView(AuditedModelViewSet):
    # ListCreateAPIView
    queryset = User.objects.filter(userType="Staff")
    serializer_class = StaffSerializer
    parser_classes = [MultiPartParser, FormParser]

    permission_classes = [IsAuthenticated]


class StaffDetailView(generics.RetrieveUpdateDestroyAPIView):

    queryset = User.objects.filter(userType="Staff")
    serializer_class = StaffSerializer
    lookup_field = "id"

    parser_classes = [MultiPartParser, FormParser]

    permission_classes = [IsAuthenticated]


class BackendUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = BackendUserSerializer
    permission_classes = [IsAuthenticatedAndStaff]

    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_context(self):
        return {"request": self.request}


class UpdateStaffView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BackendUserSerializer
    permission_classes = [IsSuperAdmin]
    lookup_field = "id"
    parser_classes = [MultiPartParser, FormParser]  # IMPORTANT

    def get_queryset(self):
        log_user_activity(self.request, f"View All Permission")
        return User.objects.all()

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        # Log the activity for retrieving a location
        log_user_activity(self.request, f"Viewed User ID: {kwargs['id']}")
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        # Log the activity for updating a location
        log_user_activity(self.request, f"Updated User ID: {kwargs['id']}")
        return response


class CreateAdminPermissionView(generics.ListAPIView):
    queryset = Access.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsSuperAdmin]

    def get_serializer_context(self):
        # Pass the request object to the serializer context
        return {"request": self.request}


class UpdatePermissionView(APIView):
    permission_classes = [IsSuperAdmin]

    def patch(self, request, user_id):

        try:
            access = Access.objects.get(user_id=user_id)
        except Access.DoesNotExist:
            return Response({"error": "Permission not found"}, status=404)

        field = request.data.get("field")

        if field not in [
            "waybill",
            "users",
            "account",
            "operations",
            "customer",
            "reports",
            "settings",
            "dispatcher",
        ]:
            return Response({"error": "Invalid permission"}, status=400)

        current_value = getattr(access, field)
        setattr(access, field, not current_value)

        access.updatedBy = request.user.username
        access.save()

        return Response(PermissionSerializer(access).data)


class AssigningPermissions(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AccessSerializer
    permission_classes = [IsSuperAdmin]
    lookup_field = "id"

    def get_queryset(self):
        log_user_activity(self.request, f"View All Permission")
        return Access.objects.all()

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        # Log the activity for retrieving a location
        log_user_activity(self.request, f"Viewed Permission ID: {kwargs['id']}")
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        # Log the activity for updating a location
        log_user_activity(self.request, f"Updated Permission ID: {kwargs['id']}")
        return response


@api_view(["GET"])
def getUserPermission(request, id):
    if request.user.is_authenticated:
        try:
            user = Access.objects.get(user_id=id)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = AccessSerializer(user)
        return Response(serializer.data)
    else:
        return Response(status=status.HTTP_401_UNAUTHORIZED)


class BackendUserDetails(generics.RetrieveUpdateAPIView):
    serializer_class = BackendUserSerializer
    permission_classes = [IsAuthenticatedAndStaff]
    lookup_field = "id"

    def get_queryset(self):
        log_user_activity(self.request, f"View All User")
        return User.objects.all()

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        # Log the activity for retrieving a location
        log_user_activity(self.request, f"Viewed User ID: {kwargs['id']}")
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        # Log the activity for updating a location
        log_user_activity(self.request, f"Updated User ID: {kwargs['id']}")
        return response


class GetAllStaff(generics.ListAPIView):
    # queryset = User.objects.filter(userType= 'Staff').all();
    serializer_class = GetStaffList
    permission_classes = [IsAuthenticatedAndStaff]
    queryset = (
        User.objects.filter(userType="Staff")
        .prefetch_related("access")
        .order_by("fullName")
        .all()
    )
    # queryset = User.objects.filter(userType='Staff').annotate(
    #     first_access=Subquery(
    #         Access.objects.filter(user_id=OuterRef('id')).values('id')[:1]
    #     )
    # )


class PayGateway(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            # Fetch the object where flag = 1
            active_gateway = PayIntegration.objects.get(flag=1, company="paystack")
            # Return the object as a dictionary
            return Response(
                {
                    "company": active_gateway.company,
                    "keyMode": active_gateway.keyMode,
                    "secretKey": active_gateway.secretKey,
                }
            )
        except PayIntegration.DoesNotExist:
            return Response({"error": "No active payment gateway found."}, status=404)


class GetAllCustomer(generics.ListAPIView):
    queryset = User.objects.filter(userType="Customer").all()
    serializer_class = GetCustomerList
    permission_classes = [IsAuthenticatedAndStaff]


from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserSession, Auditlog
from .utils import get_client_ip

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")

        session = None
        session_id = None

        # 🔥 1. Extract session_id from refresh token
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                session_id = token.get("session_id", None)
            except TokenError:
                session_id = None

        # 🔥 2. Fetch session safely
        if session_id:
            session = (
                UserSession.objects.filter(id=session_id, is_active=True)
                .select_related("user")
                .first()
            )

        # 🔥 3. Close session properly
        if session:
            session.logout_time = timezone.now()
            session.is_active = False
            session.save()

        # 🔥 4. Blacklist token
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass

        # 🔥 5. Audit log
        # Auditlog.objects.create(
        #     user=request.user if request.user.is_authenticated else None,
        #     action="LOGOUT",
        #     model="AUTH",
        #     object_id=str(request.user.id) if request.user.is_authenticated else "0",
        #     ip_address=get_client_ip(request),
        #     after={
        #         "email": request.user.email if request.user.is_authenticated else None,
        #         "login_time": session.login_time.isoformat() if session else None,
        #         "logout_time": timezone.now().isoformat(),
        #         "session_id": str(session.id) if session else None,
        #         "session_duration_seconds": (
        #             session.duration_seconds() if session else None
        #         ),
        #         "user_agent": request.META.get("HTTP_USER_AGENT"),
        #     },
        # )
        # 🔥 5. Audit log
        logout_user = (
            session.user
            if session
            else (request.user if request.user.is_authenticated else None)
        )

        Auditlog.objects.create(
            user=logout_user,
            action="LOGOUT",
            model="AUTH",
            object_id=str(logout_user.id) if logout_user else "0",
            ip_address=get_client_ip(request),
            after={
                "email": logout_user.email if logout_user else None,
                "login_time": session.login_time.isoformat() if session else None,
                "logout_time": timezone.now().isoformat(),
                "session_id": str(session.id) if session else None,
                "session_duration_seconds": (
                    session.duration_seconds() if session else None
                ),
                "user_agent": request.META.get("HTTP_USER_AGENT"),
            },
        )
        response = Response({"message": "Logout successful"}, status=200)

        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")

        return response


# class LogoutView(APIView):
#     permission_classes = [AllowAny]

#     def post(self, request):
#         refresh_token = request.COOKIES.get("refresh_token")

#         session = None

#         # 🔥 Get session from JWT (best practice)
#         try:
#             session_id = request.auth.get("session_id") if request.auth else None
#             if session_id:
#                 session = UserSession.objects.filter(id=session_id, is_active=True).first()
#         except Exception:
#             session = None

#         # 🔥 Close session if exists
#         if session:
#             session.logout_time = timezone.now()
#             session.is_active = False
#             session.save()

#         # 🔥 Blacklist token
#         if refresh_token:
#             try:
#                 token = RefreshToken(refresh_token)
#                 token.blacklist()
#             except Exception:
#                 pass

#         # 🔥 Audit log (now enriched with session data)
#         Auditlog.objects.create(
#             user=request.user if request.user.is_authenticated else None,
#             action="LOGOUT",
#             model="AUTH",
#             object_id=str(request.user.id) if request.user.is_authenticated else "0",
#             ip_address=get_client_ip(request),
#             after={
#                 "email": request.user.email if request.user.is_authenticated else None,
#                 "logout_time": timezone.now().isoformat(),
#                 "session_id": str(session.id) if session else None,
#                 "session_duration_seconds": session.duration_seconds() if session else None,
#                 "user_agent": request.META.get("HTTP_USER_AGENT"),
#             }
#         )

#         # 🔥 Response
#         response = Response(
#             {"message": "Logout successful"},
#             status=status.HTTP_200_OK
#         )

#         # 🔥 Clear cookies
#         response.delete_cookie("access_token")
#         response.delete_cookie("refresh_token")

#         return response
# class LogoutView(APIView):
#     permission_classes = [AllowAny]

#     def post(self, request):
#         refresh_token = request.COOKIES.get("refresh_token")

#         if not refresh_token:
#             response = Response(
#                 {"message": "Logged out (no refresh token)"},
#                 status=status.HTTP_200_OK
#             )
#         else:
#             try:
#                 token = RefreshToken(refresh_token)
#                 token.blacklist()
#                 Auditlog.objects.create(
#                     user=request.user,
#                     action="LOGOUT",
#                     model="AUTH",
#                     object_id=str(request.user.id),
#                     ip_address=get_client_ip(request),
#                     after={
#                         "email": request.user.email,
#                         "logout_time": timezone.now().isoformat(),
#                         "session_status": "terminated",
#                         "user_agent": request.META.get("HTTP_USER_AGENT"),
#                     }
#                 )
#                 response = Response(
#                     {"message": "Logout successfully"},
#                     status=status.HTTP_200_OK
#                 )
#             except Exception:
#                 response = Response(
#                     {"message": "Token already invalid"},
#                     status=status.HTTP_200_OK
#                 )

#         # ✅ VERY IMPORTANT: delete cookies
#         response.delete_cookie("access_token")
#         response.delete_cookie("refresh_token")

#         return response

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework.response import Response
from rest_framework import status
from django.middleware.csrf import get_token

from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.middleware.csrf import get_token
from django.contrib.auth import authenticate
from django.utils import timezone
from setup.models import User
import logging

logger = logging.getLogger(__name__)

from datetime import timedelta


def get_session_duration(user):
    if user.role == User.DISPATCHER:
        return timedelta(hours=12)

    return timedelta(hours=2)


class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        email = request.data.get("email")
        password = request.data.get("password")

        audit_user = User.objects.filter(email__iexact=email).first()
        user = authenticate(request, email=email, password=password)

        if not user:
            Auditlog.objects.create(
                user=audit_user,
                action="LOGIN_FAILED",
                model="AUTH",
                object_id=str(audit_user.pk) if audit_user else "0",
                ip_address=get_client_ip(request),
                after={
                    "email_attempt": email,
                    "account_exists": audit_user is not None,
                    "reason": "Invalid credentials",
                },
            )
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "Account is disabled."}, status=status.HTTP_403_FORBIDDEN
            )

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        # 🔥 STEP 1: CREATE SESSION FIRST
        # session = UserSession.objects.create(
        #     user=user,
        #     ip_address=get_client_ip(request),
        #     user_agent=request.META.get("HTTP_USER_AGENT"),
        # )

        # # 🔥 STEP 2: CREATE TOKENS
        # refresh = RefreshToken.for_user(user)
        # # attach session_id AFTER session exists
        # refresh["session_id"] = str(session.id)

        # access_token = str(refresh.access_token)

        session_duration = get_session_duration(user)
        session_expires_at = timezone.now() + session_duration

        session = UserSession.objects.create(
            user=user,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT"),
            expires_at=session_expires_at,
        )

        refresh = RefreshToken.for_user(user)
        refresh["session_id"] = str(session.id)

        # Create access token
        access_token_token = refresh.access_token

        # Make the access token expire at the session expiry
        access_token_token.set_exp(
            from_time=timezone.now(),
            lifetime=session_duration,
        )

        access_token = str(access_token_token)

        passport_url = (
            request.build_absolute_uri(user.passport.url) if user.passport else None
        )

        # 🔥 STEP 3: AUDIT LOG (LOGIN)
        Auditlog.objects.create(
            user=user,
            action="LOGIN",
            model="AUTH",
            object_id=str(user.id),
            ip_address=get_client_ip(request),
            after={
                "email": user.email,
                "login_time": timezone.now().isoformat(),
                "user_agent": request.META.get("HTTP_USER_AGENT"),
                "session_id": str(session.id),
            },
        )

        response_data = {
            "message": "Login Successful",
            "user": {
                "id": user.id,
                "fullName": user.fullName,
                "role": user.role,
                "usertype": user.userType,
                "staffNo": user.staffNo,
                "email": user.email,
                "passport": passport_url,
                "username": user.username,
                "hub_name": user.hub_name_id,
                "session_expires_at": session.expires_at.isoformat(),
            },
            "access_token": access_token,
            "refresh_token": str(refresh),
            "session_expires_at": session.expires_at.isoformat(),
        }

        response = Response(response_data, status=status.HTTP_200_OK)

        # SET COOKIES
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # True in production
            samesite="Lax",  # None in production
        )
        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            secure=False,
            samesite="Lax",
        )

        response.set_cookie(
            key="csrftoken",
            value=get_token(request),
            httponly=False,
            secure=False,
            samesite="Lax",
        )

        return response


# ----------------- REFRESH -----------------
# class CustomTokenRefreshView(TokenRefreshView):
#     def post(self, request, *args, **kwargs):
#         refresh_token = request.COOKIES.get("refresh_token")
#         if not refresh_token:
#             return Response({"detail": "Refresh token missing"}, status=401)

#         serializer = self.get_serializer(data={"refresh": refresh_token})
#         serializer.is_valid(raise_exception=True)
#         access_token = serializer.validated_data["access"]


#         response = Response({"message": "Token refreshed"})
#         response.set_cookie(
#             key="access_token",
#             value=access_token,
#             httponly=True,
#             secure=False,
#             samesite="Lax",
#         )
#         return response
class CustomTokenRefreshView(TokenRefreshView):

    def post(self, request, *args, **kwargs):

        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "Refresh token missing"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # -----------------------------------------
        # 1. Decode refresh token
        # -----------------------------------------
        try:
            refresh = RefreshToken(refresh_token)

            session_id = refresh.get("session_id")

            if not session_id:
                return Response(
                    {"detail": "Session information missing"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # -----------------------------------------
        # 2. Find active session
        # -----------------------------------------
        session = (
            UserSession.objects.select_related("user")
            .filter(
                id=session_id,
                is_active=True,
            )
            .first()
        )

        if not session:
            return Response(
                {"detail": "Session expired or logged out"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = session.user

        # -----------------------------------------
        # 3. Check current session expiry
        # -----------------------------------------
        now = timezone.now()

        if session.expires_at <= now:

            session.is_active = False
            session.logout_time = now

            session.save(
                update_fields=[
                    "is_active",
                    "logout_time",
                ]
            )

            return Response(
                {"detail": "Session expired"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # -----------------------------------------
        # 4. EXTEND SESSION
        #
        # Dispatcher  -> 12 hours
        # Others      -> 2 hours
        # -----------------------------------------
        session_duration = get_session_duration(user)

        session.expires_at = now + session_duration

        session.save(update_fields=["expires_at"])

        # -----------------------------------------
        # 5. Refresh JWT
        # -----------------------------------------
        serializer = self.get_serializer(data={"refresh": refresh_token})

        serializer.is_valid(raise_exception=True)

        access_token = serializer.validated_data["access"]

        # -----------------------------------------
        # 6. Get rotated refresh token
        # -----------------------------------------
        new_refresh_token = serializer.validated_data.get("refresh")

        # -----------------------------------------
        # 7. Make access token expire with session
        # -----------------------------------------
        access_token_token = AccessToken(access_token)

        access_token_token.set_exp(
            from_time=now,
            lifetime=session_duration,
        )

        access_token = str(access_token_token)

        # -----------------------------------------
        # 8. Response
        # -----------------------------------------
        response = Response(
            {
                "message": "Token refreshed",
                "session_expires_at": session.expires_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )

        # -----------------------------------------
        # 9. Access token cookie
        # -----------------------------------------
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # True in production
            samesite="Lax",
        )

        # -----------------------------------------
        # 10. Rotated refresh token cookie
        # -----------------------------------------
        if new_refresh_token:
            response.set_cookie(
                key="refresh_token",
                value=new_refresh_token,
                httponly=True,
                secure=False,  # True in production
                samesite="Lax",
            )

        return response


# from rest_framework_simplejwt.views import TokenRefreshView
# from rest_framework_simplejwt.tokens import RefreshToken
# from rest_framework.response import Response
# from rest_framework import status

# from setup.models import UserSession


# class CustomTokenRefreshView(TokenRefreshView):

#     def post(self, request, *args, **kwargs):

#         # -----------------------------------------
#         # 1. Get refresh token from cookie
#         # -----------------------------------------

#         refresh_token = request.COOKIES.get("refresh_token")

#         if not refresh_token:
#             return Response(
#                 {"detail": "Refresh token missing"},
#                 status=status.HTTP_401_UNAUTHORIZED,
#             )

#         # -----------------------------------------
#         # 2. Validate refresh token
#         # -----------------------------------------

#         try:
#             refresh = RefreshToken(refresh_token)

#             # -----------------------------------------
#             # 3. Get session ID from refresh token
#             # -----------------------------------------

#             session_id = refresh.get("session_id")

#             if not session_id:
#                 return Response(
#                     {"detail": "Session information missing"},
#                     status=status.HTTP_401_UNAUTHORIZED,
#                 )

#             # -----------------------------------------
#             # 4. Get active UserSession
#             # -----------------------------------------

#             session = (
#                 UserSession.objects.select_related("user")
#                 .filter(
#                     id=session_id,
#                     is_active=True,
#                 )
#                 .first()
#             )

#             if not session:
#                 return Response(
#                     {"detail": "Session expired or logged out"},
#                     status=status.HTTP_401_UNAUTHORIZED,
#                 )

#             # -----------------------------------------
#             # 5. Check server-side session expiry
#             # -----------------------------------------

#             if session.expires_at <= timezone.now():

#                 session.is_active = False
#                 session.logout_time = timezone.now()
#                 session.save(
#                     update_fields=[
#                         "is_active",
#                         "logout_time",
#                     ]
#                 )

#                 return Response(
#                     {"detail": "Session expired"},
#                     status=status.HTTP_401_UNAUTHORIZED,
#                 )

#         except Exception:
#             return Response(
#                 {"detail": "Invalid or expired refresh token"},
#                 status=status.HTTP_401_UNAUTHORIZED,
#             )

#         # -----------------------------------------
#         # 6. Let SimpleJWT perform the refresh
#         # -----------------------------------------

#         serializer = self.get_serializer(data={"refresh": refresh_token})

#         serializer.is_valid(raise_exception=True)

#         access_token = serializer.validated_data["access"]

#         # -----------------------------------------
#         # 7. Get rotated refresh token
#         # -----------------------------------------

#         new_refresh_token = serializer.validated_data.get("refresh")

#         # -----------------------------------------
#         # 8. Return response
#         # -----------------------------------------

#         response = Response(
#             {
#                 "message": "Token refreshed",
#                 "session_expires_at": session.expires_at.isoformat(),
#             },
#             status=status.HTTP_200_OK,
#         )

#         # -----------------------------------------
#         # 9. Set new access token
#         # -----------------------------------------

#         response.set_cookie(
#             key="access_token",
#             value=access_token,
#             httponly=True,
#             secure=False,  # True in production
#             samesite="Lax",
#         )

#         # -----------------------------------------
#         # 10. Set rotated refresh token
#         # -----------------------------------------

#         if new_refresh_token:
#             response.set_cookie(
#                 key="refresh_token",
#                 value=new_refresh_token,
#                 httponly=True,
#                 secure=False,  # True in production
#                 samesite="Lax",
#             )

#         return response


# from rest_framework_simplejwt.views import TokenRefreshView
# from rest_framework_simplejwt.tokens import RefreshToken
# from rest_framework.response import Response

# class CookieTokenRefreshView(TokenRefreshView):
#     def post(self, request, *args, **kwargs):
#         response = super().post(request, *args, **kwargs)
#         # Set new cookies
#         if "access" in response.data:
#             response.set_cookie(
#                 "access_token",
#                 response.data["access"],
#                 httponly=True,
#                 samesite="None",
#                 secure=True,
#                 path="/",
#             )
#         if "refresh" in response.data:
#             response.set_cookie(
#                 "refresh_token",
#                 response.data["refresh"],
#                 httponly=True,
#                 samesite="None",
#                 secure=True,
#                 path="/",
#             )
#         response.data.pop("access", None)
#         response.data.pop("refresh", None)
#         return response


# ----------------- VALIDATE -----------------


# @api_view(["GET"])
# def validate_token(request):
#     from rest_framework_simplejwt.tokens import AccessToken
#     from setup.models import User

#     token = request.COOKIES.get("access_token")
#     if not token:
#         return Response({"detail": "Missing token"}, status=401)

#     try:
#         payload = AccessToken(token)
#         user = User.objects.get(id=payload["user_id"])
#         return Response(
#             {
#                 "user": {
#                     "id": user.id,
#                     "username": user.username,
#                     "email": user.email,
#                     "role": user.role,
#                     "usertype": user.userType,
#                     "fullName": user.fullName,
#                     "staffNo": user.staffNo,
#                     "passport": (
#                         request.build_absolute_uri(user.passport.url)
#                         if user.passport
#                         else None
#                     ),
#                     "hub_name": user.hub_name_id,
#                 }
#             }
#         )
#     except:
#         return Response({"detail": "Invalid or expired token"}, status=401)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def validate_token(request):
    user = request.user
    session = getattr(request, "user_session", None)

    if not session:
        return Response(
            {"detail": "Session not found"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    return Response(
        {
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "usertype": user.userType,
                "fullName": user.fullName,
                "staffNo": user.staffNo,
                "passport": (
                    request.build_absolute_uri(user.passport.url)
                    if user.passport
                    else None
                ),
                "hub_name": user.hub_name_id,
                "session_expires_at": session.expires_at.isoformat(),
            }
        }
    )


class ProtectedEndpointView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"message": "Access token is valid"}, status=200)


@api_view(["GET"])
def getUserDetails(request):
    if request.user.is_authenticated:
        try:
            user = User.objects.get(pk=request.user.id)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(user)
        return Response(serializer.data)
    else:
        return Response(status=status.HTTP_401_UNAUTHORIZED)


@api_view(["GET"])
def getUserInfo(request, id):
    if request.user.is_authenticated:
        try:
            user = User.objects.get(pk=id)
        except User.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = UserSerializer(user)
        return Response(serializer.data)
    else:
        return Response(status=status.HTTP_401_UNAUTHORIZED)


class ChangePasswordView(AuditedModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = User.objects.all().order_by("fullName")

    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            # log_user_activity(self.request, f"Password Reset done")
            return Response(
                {"detail": "Password updated successfully"}, status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        user = request.user
        serializer = UpdateProfileSerializer(
            user, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            log_user_activity(self.request, f"profile Updated")
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            # log_user_activity(self.request, f"OTP sent for Password Reset")
            serializer.save()
            return Response(
                {"detail": "OTP sent to your email."}, status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            # log_user_activity(self.request, f"Password Reset done successfully")
            serializer.save()
            return Response(
                {"detail": "Password has been reset successfully."},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreateAuditlog(generics.ListCreateAPIView):
    serializer_class = AuditlogSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        return Auditlog.objects.select_related("user").all()

    def perform_create(self, serializer):
        if serializer.is_valid():
            serializer.save(createdBy=self.request.user)
        else:
            print(serializer.errors)


class UpdateCreditLimit(APIView):
    permission_classes = [IsSuperAdmin]

    def put(self, request, id):
        user = User.objects.get(pk=id)
        serializer = UpdateCreditLimitSerializer(
            user, data=request.data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            log_user_activity(self.request, f"profile Updated")
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateBackOfficeUser(APIView):
    permission_classes = [IsSuperAdmin]

    def put(self, request, id):
        user = get_object_or_404(
            User, pk=id
        )  # Use get_object_or_404 to handle missing users gracefully
        serializer = UpdateUserSerializer(
            user, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "message": "User status updated successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateMyProfile(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):

        serializer = UpdateProfileSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)


class UpdateCustomerProfile(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):

        user = get_object_or_404(User, id=id)

        serializer = UpdateProfileSerializer(
            user, data=request.data, partial=True, context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)


@api_view(["GET"])
def audit_report(request):
    res = Auditlog.objects.select_related("user").order_by("-id").all()
    serializer = AuditlogSerializer(res, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


class StateViewSet(AuditedModelViewSet):
    queryset = NigState.objects.all().order_by("name")
    serializer_class = NigStateSerializer
    permission_classes = [IsAuthenticated]
    model_label = "NigState"

    def post(self, request):
        serializer = NigStateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # 🔥 THIS FIXES IT
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class LgaViewSet(AuditedModelViewSet):
    queryset = Lga.objects.all().order_by("name")
    serializer_class = LgaSerializer
    permission_classes = [IsAuthenticated]
    model_label = "Lga"

    def post(self, request):
        serializer = LgaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # 🔥 THIS FIXES IT
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class ZoneViewSet(AuditedModelViewSet):
    queryset = Zone.objects.all().order_by("name")
    serializer_class = ZoneSerializer
    permission_classes = [IsAuthenticated]
    model_label = "Zone"

    def post(self, request):
        serializer = ZoneSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # 🔥 THIS FIXES IT
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class PayGateway(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            # Fetch the object where flag = 1
            active_gateway = PayIntegration.objects.get(flag=1, company="paystack")
            # Return the object as a dictionary
            return Response(
                {
                    "company": active_gateway.company,
                    "keyMode": active_gateway.keyMode,
                    "secretKey": active_gateway.secretKey,
                }
            )
        except PayIntegration.DoesNotExist:
            return Response({"error": "No active payment gateway found."}, status=404)


from rest_framework import viewsets


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Auditlog.objects.all().order_by("-created_at")
    serializer_class = AuditlogSerializer


class ActiveUserSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = (
            UserSession.objects.filter(is_active=True)
            .select_related("user")
            .order_by("-login_time")
        )

        serializer = ActiveSessionSerializer(sessions, many=True)

        return Response(serializer.data)


class TerminateSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        session = UserSession.objects.filter(id=id, is_active=True).first()

        if not session:
            return Response({"error": "Session not found"}, status=404)

        session.is_active = False
        session.logout_time = timezone.now()
        session.save()

        Auditlog.objects.create(
            user=request.user,
            action="LOGOUT",
            model="AUTH",
            object_id=str(session.user.id),
            ip_address=get_client_ip(request),
            after={
                "email": session.user.email,
                "logout_time": session.logout_time.isoformat(),
                "session_id": str(session.id),
                "terminated_by_admin": True,
            },
        )

        return Response({"message": "Session terminated"}, status=200)


class BankViewSet(AuditedModelViewSet):
    queryset = Bank.objects.all().order_by("name")
    serializer_class = BankSerializer
    permission_classes = [IsAuthenticated]
    model_label = "Bank"

    def post(self, request):
        serializer = BankSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # 🔥 THIS FIXES IT
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class ExpenseCategoryViewSet(AuditedModelViewSet):
    queryset = ExpenseCategory.objects.all().order_by("name")
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated]
    model_label = "ExpenseCategory"

    def post(self, request):
        serializer = ExpenseCategorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # 🔥 THIS FIXES IT
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class AllowanceDeductionViewSet(AuditedModelViewSet):
    queryset = AllowanceDeduction.objects.all().order_by("name")
    serializer_class = AllowanceDeductionSerializer
    permission_classes = [IsAuthenticated]
    model_label = "AllowanceDeduction"

    def post(self, request):
        serializer = AllowanceDeductionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # 🔥 THIS FIXES IT
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    def get_queryset(self):
        queryset = super().get_queryset()
        action_param = self.request.query_params.get("action")

        if action_param:
            queryset = queryset.filter(allowDed__iexact=action_param)

        return queryset


class PricingViewSet(AuditedModelViewSet):
    queryset = Pricing.objects.all().order_by("subarea")
    serializer_class = PricingSerializer
    permission_classes = [IsAuthenticated]
    model_label = "Pricing"

    def post(self, request):
        serializer = PricingSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()  # 🔥 THIS FIXES IT
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=False, methods=["post"], url_path="bulk-upload")
    def bulk_upload(self, request):

        data = request.data.get("data", [])

        objs = []

        for item in data:
            objs.append(
                Pricing(
                    subarea=item.get("subarea"),
                    basekg=item.get("basekg"),
                    price=item.get("price"),
                    extrakg=item.get("extrakg"),
                    extraprice=item.get("extraprice"),
                    pricetype=item.get("pricetype"),
                    createdBy_id=item.get("createdBy"),
                )
            )
            existing = Pricing.objects.filter(
                subarea__iexact=item.get("subarea")
            ).exists()

            if existing:
                continue
        Pricing.objects.bulk_create(objs)

        return Response({"detail": "Uploaded successfully"})


# views.py

from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser

from .serializers import ResetUserPasswordSerializer

User = get_user_model()


class ResetUserPasswordView(AuditedModelViewSet):
    permission_classes = [IsAdminUser]
    queryset = User.objects.all().order_by("fullName")

    def post(self, request):
        serializer = ResetUserPasswordSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data["user"]
            new_password = serializer.validated_data["new_password"]

            before = {"password": "***hidden***"}

            user.set_password(new_password)
            user.save()

            # after = {"password": "***changed***"}
            after = {
                "target_user": {
                    "id": user.id,
                    "name": user.fullName,
                    "login": user.username,
                },
                "password": "***changed***",
            }

            self.log_action(
                request=request,
                action="PASSWORD_RESET",
                instance=user,
                before=before,
                after=after,
                changes={
                    "password": {
                        "from": "***hidden***",
                        "to": "***changed***",
                    }
                },
            )

            return Response(
                {"message": "Password reset successfully."},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# views.py

from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from .models import NotificationConfig
from .serializers import NotificationConfigSerializer


class NotificationConfigView(APIView):

    permission_classes = [IsAdminUser]

    def get(self, request):

        config = NotificationConfig.objects.filter(is_active=True).first()

        if not config:
            config = NotificationConfig.objects.create(channel="EMAIL", is_active=True)

        serializer = NotificationConfigSerializer(config)

        return Response(serializer.data)

    def patch(self, request):

        config = NotificationConfig.objects.filter(is_active=True).first()

        if not config:
            config = NotificationConfig.objects.create(channel="EMAIL")

        serializer = NotificationConfigSerializer(
            config, data=request.data, partial=True
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)


from rest_framework.permissions import IsAdminUser
from rest_framework.viewsets import ModelViewSet


from rest_framework.viewsets import ModelViewSet


class NotificationTypeViewSet(AuditedModelViewSet):

    queryset = NotificationType.objects.all()

    serializer_class = NotificationTypeSerializer

    permission_classes = [IsAdminUser]

    http_method_names = [
        "get",
        "patch",
        "head",
        "options",
    ]


class NotificationLogListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]

    serializer_class = NotificationLogSerializer

    queryset = NotificationLog.objects.all().order_by("-created_at")


class NotificationTemplateViewSet(AuditedModelViewSet):

    queryset = NotificationTemplate.objects.select_related("notification_type").all()

    serializer_class = NotificationTemplateSerializer

    permission_classes = [IsAdminUser]

    http_method_names = [
        "get",
        "patch",
        "post",
        "head",
        "options",
    ]


from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from setup.models import User, Auditlog


class GeneralNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):

        user_ids = request.data.get("user_ids", [])
        message = request.data.get("message", "").strip()

        # ==========================================
        # 1. VALIDATE MESSAGE
        # ==========================================

        if not message:
            return Response(
                {"message": "Notification message is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 2. VALIDATE RECIPIENTS
        # ==========================================

        if not user_ids or not isinstance(user_ids, list):
            return Response(
                {"message": "At least one recipient is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 3. GET ACTIVE USERS
        # ==========================================

        users = User.objects.filter(
            id__in=user_ids,
            is_active=True,
        )

        if not users.exists():
            return Response(
                {"message": "No active recipients found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 4. SEND NOTIFICATION
        # ==========================================

        sent_to = 0
        failed = 0

        for user in users:

            context = {
                "receiver": user.fullName or user.email,
                "message": message,
            }

            sms_recipients = []

            if user.mobileNo:
                sms_recipients.append(user.mobileNo)

            try:
                send_notification(
                    notification_type="GENERAL_NOTIFICATION",
                    context=context,
                    receiver_email=user.email,
                    receiver_phone=user.mobileNo,
                    sms_recipients=sms_recipients,
                )

                sent_to += 1

            except Exception:
                failed += 1

        # ==========================================
        # 5. AUDIT
        # ==========================================

        Auditlog.objects.create(
            user=request.user,
            action="GENERAL_NOTIFICATION",
            model="Notification",
            object_id="GENERAL",
            after={
                "recipients": [str(user.id) for user in users],
                "recipient_count": users.count(),
                "message": message,
            },
            ip_address=get_client_ip(request),
        )

        return Response(
            {
                "message": "General notification processed successfully.",
                "recipients": users.count(),
                "processed": sent_to,
                "failed": failed,
            },
            status=status.HTTP_200_OK,
        )


class CampaignNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):

        audience = request.data.get("audience")
        role = request.data.get("role")
        user_ids = request.data.get("user_ids", [])
        message = request.data.get("message", "").strip()

        # ==========================================
        # 1. VALIDATE MESSAGE
        # ==========================================

        if not message:
            return Response(
                {"message": "Campaign message is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 2. VALIDATE AUDIENCE
        # ==========================================

        allowed_audiences = [
            "ALL",
            "ALL_CUSTOMERS",
            "ALL_STAFF",
            "ROLE",
            "SELECTED",
        ]

        if audience not in allowed_audiences:
            return Response(
                {"message": "Invalid campaign audience."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 3. BUILD RECIPIENT QUERY
        # ==========================================

        users = User.objects.filter(is_active=True)

        if audience == "ALL_CUSTOMERS":

            users = users.filter(userType=User.CUSTOMER)

        elif audience == "ALL_STAFF":

            users = users.filter(userType=User.STAFF)

        elif audience == "ROLE":

            if not role:
                return Response(
                    {"message": "Role is required for role-based campaigns."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            users = users.filter(role=role)

        elif audience == "SELECTED":

            if not user_ids or not isinstance(user_ids, list):
                return Response(
                    {"message": "Select at least one user."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            users = users.filter(id__in=user_ids)

        # ==========================================
        # 4. CHECK RECIPIENTS
        # ==========================================

        if not users.exists():
            return Response(
                {"message": "No active recipients found for this campaign."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 5. SEND CAMPAIGN
        # ==========================================

        processed = 0
        failed = 0

        for user in users:

            context = {
                "receiver": user.fullName or user.email,
                "message": message,
            }

            sms_recipients = []

            if user.mobileNo:
                sms_recipients.append(user.mobileNo)

            try:

                send_notification(
                    notification_type="CAMPAIGN",
                    context=context,
                    receiver_email=user.email,
                    receiver_phone=user.mobileNo,
                    sms_recipients=sms_recipients,
                )

                processed += 1

            except Exception:
                failed += 1

        # ==========================================
        # 6. AUDIT
        # ==========================================

        Auditlog.objects.create(
            user=request.user,
            action="CAMPAIGN_NOTIFICATION",
            model="Notification",
            object_id="CAMPAIGN",
            after={
                "audience": audience,
                "role": role,
                "recipient_count": users.count(),
                "message": message,
            },
            ip_address=get_client_ip(request),
        )

        return Response(
            {
                "message": "Campaign processed successfully.",
                "audience": audience,
                "recipients": users.count(),
                "processed": processed,
                "failed": failed,
            },
            status=status.HTTP_200_OK,
        )


class SendGeneralNotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        recipient_type = request.data.get("recipient_type")
        role = request.data.get("role")
        hub_id = request.data.get("hub_id")
        user_ids = request.data.get("user_ids", [])

        if not recipient_type:
            return Response(
                {"message": "Recipient type is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed_types = [
            "ALL",
            "CUSTOMERS",
            "STAFF",
            "ROLE",
            "HUB",
            "USERS",
        ]

        if recipient_type not in allowed_types:
            return Response(
                {"message": "Invalid recipient type."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if recipient_type == "ROLE" and not role:
            return Response(
                {"message": "Role is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if recipient_type == "HUB" and not hub_id:
            return Response(
                {"message": "Hub is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if recipient_type == "USERS" and not user_ids:
            return Response(
                {"message": "At least one user must be selected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        users = get_notification_recipients(
            recipient_type=recipient_type,
            role=role,
            hub_id=hub_id,
            user_ids=user_ids,
        )

        if not users.exists():
            return Response(
                {"message": "No active users found for the selected recipients."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        context = {
            "subject": request.data.get("subject", ""),
            "message": request.data.get("message", ""),
            "sender": request.user.fullName or request.user.get_user_fullname,
            "sender_email": request.user.email,
        }

        notification_type = request.data.get(
            "notification_type",
            "GENERAL_NOTIFICATION",
        )

        result = send_bulk_notification(
            notification_type=notification_type,
            users=users,
            context=context,
        )

        return Response(
            {
                "message": "Notification processing completed.",
                **result,
            },
            status=status.HTTP_200_OK,
        )
