import json

from rest_framework import serializers
from django.contrib.auth import get_user_model

from hmcs.models import AllowanceDeduction
from .models import (
    Access,
    Auditlog,
    Bank,
    ExpenseCategory,
    NigState,
    PayIntegration,
    UserSession,
    Zone,
    Lga,
    Pricing,
)
import random
from django.core.mail import send_mail
from .utils import generate_staffNo, log_activity, log_user_activity
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import make_password
from django.db import transaction, IntegrityError
from rest_framework.validators import UniqueValidator
from decimal import Decimal
import uuid

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="Account already exists with this email.",
            )
        ]
    )
    hub_info = serializers.CharField(source="hub_name.hubName", read_only=True)
    mobileNo = serializers.CharField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="Account already exists with this mobile number.",
            )
        ]
    )

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "password",
            "staffNo",
            "email",
            "userType",
            "mobileNo",
            "role",
            "customerType",
            "sex",
            "haddress",
            "altphone",
            "fullName",
            "passport",
            "cPayType",
            "date_joined",
            "is_active",
            "creditLimit",
            "last_login",
            "api_base_url",
            "api_key",
            "auth_type",
            "hub_name",
            "hub_info",
        ]
        # fields = "__all__"
        extra_kwargs = {
            "password": {"write_only": True},
            "date_joined": {"required": False},
            "is_active": {"required": False},
            "creditLimit": {"required": False},
            "last_login": {"read_only": True, "required": False},
            "passport": {"required": False},
            "api_base_url": {"required": False},
            "api_key": {"required": False},
            "auth_type": {"required": False},
            "hub_name": {"required": False},
            "hub_info": {"required": False},
        }

    def validate_email(self, value):
        return value.strip().lower()

    def validate_mobileNo(self, value):
        return value.strip()

    def validate(self, data):
        email = data.get("email")
        mobile = data.get("mobileNo")

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                {"email": "Account already exists with this email."}
            )

        if mobile and User.objects.filter(mobileNo=mobile).exists():
            raise serializers.ValidationError(
                {"mobileNo": "Account already exists with this mobile number."}
            )
        return data

    def create(self, validated_data):
        validated_data["username"] = validated_data.get("email")
        password = validated_data.pop("password")
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=validated_data["username"],
                    email=validated_data.get("email"),
                    password=password,
                    first_name=validated_data.get("first_name", ""),
                    last_name=validated_data.get("last_name", ""),
                    userType=validated_data.get("userType", "Customer"),
                    mobileNo=validated_data.get("mobileNo", ""),
                    role=validated_data.get("role", ""),
                    haddress=validated_data.get("haddress", ""),
                    customerType=validated_data.get("customerType", "Personal"),
                    sex=validated_data.get("sex", ""),
                    fullName=validated_data.get("cperson", ""),
                    cPayType=validated_data.get("cPayType", "Prepaid"),
                )
                if user.userType == "Customer" or user.userType is None:
                    user.staffNo = generate_staffNo("PWC", "custno")
                    user.role = "Customer"
                    user.fullName = user.first_name + "" + user.last_name
                else:
                    user.staffNo = generate_staffNo("PWS", "staffno")
                    user.userType = "Staff"
                    user.is_staff = True

                if user.userType == "Customer" and user.customerType == "Personal":
                    user.fullName = user.get_user_fullname
                else:
                    user.fullName = user.first_name + "" + user.last_name

                # if len(user.fullName) > 20:
                #     user.displayName = user.first_name
                # else:
                #     user.displayName = user.fullName
                user.save()
                return user

        except IntegrityError:
            raise serializers.ValidationError({"detail": "Account already exists."})

    def validate(self, data):
        role = data.get("role")
        dispatcher_type = data.get("dispatcher_type")
        partner = data.get("partner")

        if role == "Dispatcher":
            if dispatcher_type == "External" and not partner:
                raise serializers.ValidationError(
                    "External dispatcher must have a partner"
                )

            if dispatcher_type == "Internal" and partner:
                raise serializers.ValidationError(
                    "Internal dispatcher should not have a partner"
                )

        return data


class AccessSerializer(serializers.ModelSerializer):

    class Meta:
        model = Access
        fields = [
            "waybill",
            "users",
            "account",
            "operations",
            "customer",
            "reports",
            "settings",
        ]


class PermissionSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.get_full_name")
    role = serializers.CharField(source="user.role", read_only=True)

    class Meta:
        model = Access
        fields = [
            "user_id",
            "user",
            "waybill",
            "users",
            "account",
            "operations",
            "customer",
            "reports",
            "settings",
            "role",
        ]


class StaffSerializer(serializers.ModelSerializer):
    waybill = serializers.BooleanField(required=False)
    users = serializers.BooleanField(required=False)
    account = serializers.BooleanField(required=False)
    operations = serializers.BooleanField(required=False)
    customer = serializers.BooleanField(required=False)
    reports = serializers.BooleanField(required=False)
    settings = serializers.BooleanField(required=False)
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    hub_info = serializers.CharField(source="hub_name.hubName", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "mobileNo",
            "staffNo",
            "is_active",
            "fullName",
            "sex",
            "role",
            "passport",
            "password",
            "dispatcher_type",
            "partner",
            "partner_name",
            "assignedVehicle",
            # "access",
            "waybill",
            "users",
            "account",
            "operations",
            "customer",
            "reports",
            "settings",
            "hub_name",
            "hub_info",
            "monthly_pay",
            "paystaff",
            "kin",
            "kin_phone",
            "kin_address",
            "kin_relationship",
            "marital_status",
            "dob",
            "bank",
            "account_no",
            "disengagement_date",
            "guarantor",
            "guarantor_add",
            "guarantor_mobile",
            "guarantor_rship",
            "guarantor_nin",
            "item",
        ]

        extra_kwargs = {
            "password": {"write_only": True, "required": False},
            "dispatcher_type": {"required": False},
            "partner": {"required": False},
            "partner_name": {"required": False},
            "assignedVehicle": {"required": False},
            "hub_name": {"required": False},
            "hub_info": {"required": False},
            "monthly_pay": {"required": False},
            "paystaff": {"required": False},
            "kin": {"required": False},
            "kin_phone": {"required": False},
            "kin_address": {"required": False},
            "kin_relationship": {"required": False},
            "marital_status": {"required": False},
            "dob": {"required": False},
            "bank": {"required": False},
            "account_no": {"required": False},
            "disengagement_date": {"required": False},
            "guarantor": {"required": False},
            "guarantor_add": {"required": False},
            "guarantor_mobile": {"required": False},
            "guarantor_rship": {"required": False},
            "guarantor_nin": {"required": False},
            "item": {"required": False},
        }

    def to_internal_value(self, data):

        access = data.get("access")

        if isinstance(access, str):
            data["access"] = json.loads(access)

        return super().to_internal_value(data)

    def validate_email(self, value):

        if self.instance:
            if User.objects.exclude(pk=self.instance.pk).filter(email=value).exists():
                raise serializers.ValidationError("Email already exists")
        else:
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError("Email already exists")

        return value

    def create(self, validated_data):

        access_data = {
            "waybill": validated_data.pop("waybill", False),
            "users": validated_data.pop("users", False),
            "account": validated_data.pop("account", False),
            "operations": validated_data.pop("operations", False),
            "customer": validated_data.pop("customer", False),
            "reports": validated_data.pop("reports", False),
            "settings": validated_data.pop("settings", False),
        }

        password = validated_data.pop("password")

        validated_data["username"] = validated_data["email"]
        validated_data["userType"] = "Staff"

        user = User.objects.create_user(password=password, **validated_data)

        user.staffNo = generate_staffNo("PWS", "staffno")
        user.fullName = f"{user.first_name} {user.last_name}"
        user.is_staff = True
        user.save()

        Access.objects.create(
            user=user, createdBy=self.context["request"].user.username, **access_data
        )

        return user

    def update(self, instance, validated_data):

        access_data = {
            "waybill": validated_data.pop("waybill", None),
            "users": validated_data.pop("users", None),
            "account": validated_data.pop("account", None),
            "operations": validated_data.pop("operations", None),
            "customer": validated_data.pop("customer", None),
            "reports": validated_data.pop("reports", None),
            "settings": validated_data.pop("settings", None),
        }

        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.fullName = f"{instance.first_name} {instance.last_name}"
        instance.save()

        access_obj, _ = Access.objects.get_or_create(user=instance)

        for key, value in access_data.items():
            if value is not None:
                setattr(access_obj, key, value)

        access_obj.updatedBy = self.context["request"].user.username
        access_obj.save()

        return instance


class GetStaffList(serializers.ModelSerializer):

    access = serializers.SerializerMethodField()
    partner_name = serializers.CharField(source="partner.name", read_only=True)
    hub_info = serializers.CharField(source="hub_name.hubName", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "mobileNo",
            "sex",
            "role",
            "passport",
            "staffNo",
            "is_active",
            "dispatcher_type",
            "partner",
            "partner_name",
            "fullName",
            "access",
            "assignedVehicle",
            "hub_name",
            "hub_info",
            "monthly_pay",
            "paystaff",
            "kin",
            "kin_phone",
            "kin_address",
            "kin_relationship",
            "marital_status",
            "dob",
            "bank",
            "account_no",
            "disengagement_date",
            "guarantor",
            "guarantor_add",
            "guarantor_mobile",
            "guarantor_rship",
            "guarantor_nin",
            "item",
        ]

    def get_partner_name(self, obj):
        if obj.partner:
            return obj.partner.name
        return None  # ✅ Always return somethi

    def get_access(self, obj):
        access = Access.objects.filter(user=obj).first()

        if not access:
            return None

        return {
            "waybill": access.waybill,
            "users": access.users,
            "account": access.account,
            "operations": access.operations,
            "customer": access.customer,
            "reports": access.reports,
            "settings": access.settings,
        }


class BackendUserSerializer(serializers.ModelSerializer):

    waybill = serializers.BooleanField(required=False)
    users = serializers.BooleanField(required=False)
    account = serializers.BooleanField(required=False)
    operations = serializers.BooleanField(required=False)
    customer = serializers.BooleanField(required=False)
    reports = serializers.BooleanField(required=False)
    settings = serializers.BooleanField(required=False)

    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="Account already exists with this email.",
            )
        ]
    )

    mobileNo = serializers.CharField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="Account already exists with this mobile number.",
            )
        ]
    )

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "password",
            "email",
            "userType",
            "mobileNo",
            "role",
            "customerType",
            "sex",
            "haddress",
            "altphone",
            "fullName",
            "passport",
            "cPayType",
            "waybill",
            "users",
            "account",
            "operations",
            "customer",
            "reports",
            "settings",
        ]

        extra_kwargs = {"password": {"write_only": True, "required": False}}

    def create(self, validated_data):

        access_data = {
            "waybill": validated_data.pop("waybill", False),
            "users": validated_data.pop("users", False),
            "account": validated_data.pop("account", False),
            "operations": validated_data.pop("operations", False),
            "customer": validated_data.pop("customer", False),
            "reports": validated_data.pop("reports", False),
            "settings": validated_data.pop("settings", False),
        }

        password = validated_data.pop("password")

        validated_data["username"] = validated_data["email"]

        with transaction.atomic():

            user = User.objects.create_user(password=password, **validated_data)

            user.fullName = f"{user.first_name} {user.last_name}"

            if user.userType == "Staff":
                user.staffNo = generate_staffNo("PWS", "staffno")
                user.is_staff = True

            user.save()

            Access.objects.create(
                user=user,
                createdBy=self.context["request"].user.username,
                **access_data,
            )

        return user

    def update(self, instance, validated_data):

        access_data = {
            "waybill": validated_data.pop("waybill", None),
            "users": validated_data.pop("users", None),
            "account": validated_data.pop("account", None),
            "operations": validated_data.pop("operations", None),
            "customer": validated_data.pop("customer", None),
            "reports": validated_data.pop("reports", None),
            "settings": validated_data.pop("settings", None),
        }

        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.fullName = f"{instance.first_name} {instance.last_name}"
        instance.save()

        access_obj, _ = Access.objects.get_or_create(user=instance)

        for key, value in access_data.items():
            if value is not None:
                setattr(access_obj, key, value)

        access_obj.updatedBy = self.context["request"].user.username
        access_obj.save()

        return instance


class GetCustomerList(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "fullName",
            "sex",
            "passport",
            "customerType",
            "userType",
            "createdBy",
            "mobileNo",
            "is_active",
            "creditLimit",
            "staffNo",
            "cPayType",
            "role",
            "haddress",
            "api_base_url",
            "api_key",
            "auth_type",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, data):
        user = self.context["request"].user
        if not user.check_password(data["old_password"]):
            raise serializers.ValidationError({"detail": "Old password is incorrect"})
        return data

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user


class UpdateProfileSerializer(serializers.ModelSerializer):
    passport = serializers.ImageField(required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "fullName",
            "sex",
            "passport",
            "customerType",
            "userType",
            "createdBy",
            "mobileNo",
            "is_active",
            "creditLimit",
            "staffNo",
            "cPayType",
            "role",
            "haddress",
            "altphone",
            "api_base_url",
            "api_key",
            "auth_type",
            "assignedVehicle",
            "hub_name",
        ]

        extra_kwargs = {
            "password": {"write_only": True, "required": False},
            "staffNo": {"required": False, "allow_blank": True},
            "mobileNo": {"required": False, "allow_blank": True},
            "altphone": {"required": False, "allow_blank": True},
            "api_base_url": {"required": False, "allow_blank": True},
            "api_key": {"required": False, "allow_blank": True},
            "auth_type": {"required": False, "allow_blank": True},
            "assignedVehicle": {"required": False, "allow_blank": True},
            "hub_name": {"required": False, "allow_blank": True},
        }

    def to_representation(self, instance):
        """Customize response to exclude sensitive fields and include passport URL."""
        data = super().to_representation(instance)

        data.pop("password", None)

        request = self.context.get("request")

        if instance.passport and hasattr(instance.passport, "url"):
            data["passport_url"] = request.build_absolute_uri(instance.passport.url)
        else:
            data["passport_url"] = None

        return data

    def validate_email(self, value):
        """
        Ensure email is unique but allow updating own email.
        Works for both user updating themselves and staff updating customers.
        """
        instance = getattr(self, "instance", None)

        if User.objects.exclude(pk=instance.pk).filter(email=value).exists():
            raise serializers.ValidationError("This email is already in use.")

        return value

    def update(self, instance, validated_data):

        passport = validated_data.pop("passport", None)

        # Update fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Handle passport upload
        if passport:

            # Delete old passport
            if instance.passport and instance.passport.name != passport.name:
                instance.passport.delete(save=False)

            instance.passport = passport

        instance.save()

        return instance


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user is associated with this email.")
        return value

    def save(self):
        user = User.objects.get(email=self.validated_data["email"])

        # Generate OTP
        otp = str(random.randint(100000, 999999))
        user.otp = otp
        user.otp_created_at = timezone.now()
        user.save()
        # ✅ Log activity
        log_activity(self.context.get("request"), user, "Password reset OTP sent")

        subject = "Paveway Logistics Password Reset OTP"
        from_email = "Paveway Logistics <eplatformapp@gmail.com>"
        to_email = [user.email]

        # Context for template
        context = {"user": user, "otp": otp, "year": datetime.now().year}

        html_content = render_to_string("emails/reset_otp.html", context)
        text_content = strip_tags(html_content)

        email = EmailMultiAlternatives(subject, text_content, from_email, to_email)
        email.attach_alternative(html_content, "text/html")
        email.send()

        return user


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def validate(self, data):
        try:
            user = User.objects.get(email=data["email"])
            # ✅ Log activity
            log_activity(self.context.get("request"), user, "OTP verified successfully")

        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email")

        if user.otp != data["otp"]:
            # ✅ Log activity
            log_activity(
                self.context.get("request"), user, "Failed OTP verification attempt"
            )
            raise serializers.ValidationError("Invalid OTP")

        if not user.is_otp_valid():
            raise serializers.ValidationError("OTP has expired")

        return data


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    password = serializers.CharField(min_length=6)

    def validate(self, data):
        try:
            user = User.objects.get(email=data["email"])
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email")

        if user.otp != data["otp"]:
            raise serializers.ValidationError("Invalid OTP")

        if not user.is_otp_valid():
            raise serializers.ValidationError("OTP expired")

        return data

    def save(self):
        user = User.objects.get(email=self.validated_data["email"])

        user.set_password(self.validated_data["password"])

        # Clear OTP after use
        user.otp = None
        user.otp_created_at = None
        user.save()

        # ✅ Log activity
        log_activity(self.context.get("request"), user, "Password reset successfully")
        return user


class AuditlogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.fullName", read_only=True)
    user_type = serializers.CharField(source="user.userType", read_only=True)
    login_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Auditlog
        fields = "__all__"


class ActiveSessionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.fullName", read_only=True)
    login_name = serializers.CharField(source="user.username", read_only=True)
    user_type = serializers.CharField(source="user.userType", read_only=True)

    class Meta:
        model = UserSession
        fields = [
            "id",
            "user_name",
            "login_name",
            "user_type",
            "ip_address",
            "login_time",
        ]


class UpdateCreditLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["creditLimit", "cPayType"]

    def update(self, instance, validated_data):
        instance.cPayType = validated_data.get("cPayType", instance.cPayType)
        instance.creditLimit = validated_data.get("creditLimit", instance.creditLimit)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["is_active"]

    def update(self, instance, validated_data):
        instance.is_active = validated_data.get("is_active", instance.is_active)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class PayIntSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayIntegration
        fields = "__all__"


class NigStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NigState
        fields = ["id", "code", "name", "createdBy", "created_at", "is_active"]


class LgaSerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)

    class Meta:
        model = Lga
        fields = "__all__"
        extra_kwargs = {
            "created_at": {"required": False},
        }


class ZoneSerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)
    lga_name = serializers.CharField(source="lga.name", read_only=True)

    class Meta:
        model = Zone
        fields = "__all__"
        extra_kwargs = {
            "created_at": {"required": False},
        }


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = "__all__"
        extra_kwargs = {
            "created_at": {"required": False},
        }


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = "__all__"
        extra_kwargs = {
            "created_at": {"required": False},
        }


class AllowanceDeductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllowanceDeduction
        fields = "__all__"
        extra_kwargs = {
            "created_at": {"required": False},
        }


class PricingSerializer(serializers.ModelSerializer):
    created_user = serializers.CharField(source="createdBy.fullName", read_only=True)
    updated_user = serializers.CharField(source="updatedBy.fullName", read_only=True)

    class Meta:
        model = Pricing
        fields = [
            "id",
            "subarea",
            "price",
            "basekg",
            "extrakg",
            "extraprice",
            "pricetype",
            "createdBy",
            "updatedBy",
            "createdAt",
            "updatedAt",
            "created_user",
            "updated_user",
        ]
        extra_kwargs = {
            "createdAt": {"required": False},
            "updatedAt": {"required": False},
            "updatedBy": {"required": False},
        }
