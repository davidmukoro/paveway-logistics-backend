import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta

from pydantic import ValidationError
from django.core.exceptions import ValidationError
from logistics.models import LogisticsPartner, Hub
from django.db.models.functions import Lower

# Create your models here.


class Bank(models.Model):
    name = models.CharField(max_length=100, default="")
    code = models.CharField(max_length=20, default="")
    createdBy = models.CharField(max_length=255, null=True, blank=True)
    createdAt = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    haddress = models.CharField(
        max_length=150, blank=True, null=True
    )  # simple role field (Admin, HR, etc.)
    staffNo = models.CharField(max_length=20, unique=True, blank=True, null=True)
    passport = models.ImageField(
        upload_to="passports/", blank=True, null=True
    )  # Profile picture
    fullName = models.CharField(max_length=150, blank=True, null=True)
    otp = models.CharField(max_length=200, blank=True, null=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    mobileNo = models.CharField(max_length=15, unique=True)
    sex = models.CharField(max_length=10, null=True)
    altphone = models.CharField(max_length=11, null=True)
    customerType = models.CharField(max_length=200, default="")  # postpaid/prepaid
    creditLimit = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    cPayType = models.CharField(max_length=30, default="")  # walk-In/registered
    CUSTOMER = "Customer"
    STAFF = "Staff"
    MARKETER = "Marketer"
    CustomerMgmt = "Customer"
    ACCOUNT = "Account"
    DISPATCHER = "Dispatcher"
    SUPERADMIN = "Superadmin"

    USER_TYPE_CHOICES = [
        (CUSTOMER, "Customer"),
        (STAFF, "Staff"),
    ]
    userType = models.CharField(
        max_length=10, choices=USER_TYPE_CHOICES, default=CUSTOMER
    )
    ROLE_TYPE_CHOICES = [
        (CUSTOMER, "Customer"),
        (MARKETER, "Marketer"),
        (ACCOUNT, "Account"),
        (DISPATCHER, "Dispatcher"),
        (SUPERADMIN, "Superadmin"),
        (CustomerMgmt, "Customer"),
    ]
    role = models.CharField(max_length=25, choices=ROLE_TYPE_CHOICES, default=CUSTOMER)
    createdBy = models.CharField(max_length=255, null=True, blank=True)
    createdAt = models.DateTimeField(null=True, blank=True)
    # api
    api_base_url = models.URLField(null=True, blank=True)
    api_key = models.TextField(null=True, blank=True)  # encrypted later

    auth_type = models.CharField(max_length=20, null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    INTERNAL = "Internal"
    EXTERNAL = "External"

    DISPATCHER_TYPE_CHOICES = [
        (INTERNAL, "Internal"),
        (EXTERNAL, "External"),
    ]

    dispatcher_type = models.CharField(
        max_length=10, choices=DISPATCHER_TYPE_CHOICES, null=True, blank=True
    )
    partner = models.ForeignKey(
        LogisticsPartner,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dispatchers",
    )
    dispatcher_flag = models.CharField(
        max_length=255, default="Available", null=True, blank=True
    )
    assignedVehicle = models.CharField(max_length=255, null=True, blank=True)
    hub_name = models.ForeignKey(
        Hub, null=True, blank=True, on_delete=models.SET_NULL, related_name="user_hub"
    )
    monthly_pay = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    disengagement_date = models.DateField(null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=10, null=True)
    marital_status = models.CharField(max_length=20, null=True)
    account_no = models.CharField(max_length=255, null=True, blank=True)
    bank = models.ForeignKey(
        Bank, null=True, blank=True, on_delete=models.SET_NULL, related_name="user_bank"
    )
    kin = models.CharField(max_length=255, null=True, blank=True)
    kin_phone = models.CharField(max_length=15, null=True, blank=True)
    kin_relationship = models.CharField(max_length=50, null=True, blank=True)
    kin_address = models.CharField(max_length=255, null=True, blank=True)
    paystaff = models.BooleanField(default=False)
    guarantor = models.CharField(max_length=255, null=True, blank=True)
    guarantor_add = models.CharField(max_length=255, null=True, blank=True)
    guarantor_nin = models.CharField(max_length=255, null=True, blank=True)
    guarantor_rship = models.CharField(max_length=255, null=True, blank=True)
    guarantor_mobile = models.CharField(max_length=255, null=True, blank=True)
    item = models.TextField(max_length=700, null=True, blank=True)

    def clean(self):
        if self.role == "Dispatcher":
            if self.dispatcher_type == "External" and not self.partner:
                raise ValidationError("External dispatcher must have a partner")

            if self.dispatcher_type == "Internal" and self.partner:
                raise ValidationError("Internal dispatcher should not have a partner")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email

    @property
    def get_user_fullname(self):
        return f"{self.first_name} {self.last_name}"

    def is_otp_valid(self):
        if self.otp and self.otp_created_at:
            return timezone.now() <= self.otp_created_at + timedelta(minutes=5)
        return False


class Access(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="access")

    waybill = models.BooleanField(default=False)
    users = models.BooleanField(default=False)
    account = models.BooleanField(default=False)
    operations = models.BooleanField(default=False)
    customer = models.BooleanField(default=False)
    reports = models.BooleanField(default=False)
    settings = models.BooleanField(default=False)
    dispatcher = models.BooleanField(default=False)

    createdBy = models.CharField(max_length=100, null=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedBy = models.CharField(max_length=100, null=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "setup_access"


class Codesec(models.Model):
    code = models.CharField(max_length=100, default="")
    counter = models.IntegerField(default=0)
    year = models.IntegerField(default=0)
    lastRecord = models.CharField(max_length=100, default="")

    def __str__(self):
        return self.lastRecord


class PayIntegration(models.Model):
    company = models.CharField(max_length=200, default="")
    keyMode = models.CharField(max_length=50, default="")
    flag = models.IntegerField(default=1)
    secretKey = models.CharField(max_length=200, default="")


class NigState(models.Model):
    code = models.CharField(max_length=30, null=True)
    name = models.CharField(max_length=50, null=True)
    createdBy = models.CharField(max_length=100, null=True, default="")
    created_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.code} - {self.name}"  # Use the custom property


class Lga(models.Model):
    code = models.CharField(max_length=30, null=True)
    name = models.CharField(max_length=50, null=True)
    state = models.ForeignKey(
        NigState, default=1, on_delete=models.CASCADE, related_name="setup_state_lga"
    )
    createdBy = models.CharField(max_length=100, null=True, default="")
    created_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.code} - {self.name}"  # Use the custom property


class Zone(models.Model):
    code = models.CharField(max_length=30, null=True)
    name = models.CharField(max_length=50, null=True)
    state = models.ForeignKey(
        NigState, on_delete=models.CASCADE, related_name="setup_zone_state"
    )
    lga = models.ForeignKey(
        Lga, on_delete=models.CASCADE, related_name="setup_zone_lga"
    )
    createdBy = models.CharField(max_length=100, null=True, default="")
    created_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.code} - {self.name}"  # Use the custom property


class Auditlog(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=["model"]),
            models.Index(fields=["action"]),
            models.Index(fields=["created_at"]),
        ]

    ACTIONS = (
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("DELETE", "Delete"),
        ("RETRIEVE", "Retrieve"),
        ("LOGIN", "Login"),
        ("LOGIN_FAILED", "Login_Failed"),
        ("LOGOUT", "Logout"),
    )

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTIONS, default="RETRIEVE")
    model = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50, null=True, blank=True)

    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)

    changes = models.JSONField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def get_model_label(self):
        return getattr(
            self.queryset.model, "verbose_name", self.queryset.model.__name__
        )


class UserSession(models.Model):
    user = models.ForeignKey("setup.User", on_delete=models.CASCADE)
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def duration_seconds(self):
        if self.logout_time:
            return (self.logout_time - self.login_time).total_seconds()
        return None


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, default="")
    description = models.TextField(null=True, blank=True)
    createdBy = models.CharField(max_length=255, null=True, blank=True)
    createdAt = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Pricing(models.Model):
    subarea = models.CharField(max_length=100, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    basekg = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    extrakg = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    extraprice = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pricetype = models.CharField(max_length=100, default="")  # local/interstate
    createdBy = models.ForeignKey(
        "setup.user", on_delete=models.SET_NULL, related_name="price_creator", null=True
    )
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedBy = models.ForeignKey(
        "setup.user", on_delete=models.SET_NULL, related_name="price_updator", null=True
    )
    updatedAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("subarea"), name="unique_subarea_case_insensitive"
            )
        ]

    def __str__(self):
        return f"${self.name}- ${self.price}"
