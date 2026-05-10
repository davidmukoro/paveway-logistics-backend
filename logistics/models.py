import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta
#from setup.models import NigState, User

from pydantic import ValidationError
#from setup.models import NigState,Lga,User,Zone

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey("setup.User", on_delete=models.CASCADE, related_name='vendor_orders')
    order_no = models.CharField(max_length=100,null=True)# orderNo+vendor_order_no
    vendor_order_no = models.CharField(max_length=100)# order No coming from vendors
    createdBy = models.ForeignKey("setup.User",on_delete=models.SET_NULL,null=True,blank=True,related_name="orders_created"
)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.order_no:
            self.order_no = f"{self.vendor.staffNo}-{self.vendor_order_no}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vendor_order_no}"
    
class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    barcode = models.CharField(max_length=200, unique=True, db_index=True)
    description = models.TextField(null=True, blank=True)
    is_scanned = models.BooleanField(default=True)
    scanned_at = models.DateTimeField(auto_now_add=True)
    qty = models.IntegerField(default=1,null=True, blank=True)
    itemimg =  models.ImageField(upload_to='orders/', blank=True, null=True)
    STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('IN_TRANSIT', 'In Transit'),
    ('SCANNED_IN', 'Scanned In'),
    ('WAREHOUSE', 'Warehouse'),
    ('OUT_FOR_DELIVERY', 'Out for Delivery'),
    ('INWARD_RETURNED', 'Inward Returned'),
    ('OUTWARD_RETURNED', 'Outward Returned'),
]

    flag = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING')#Intransit, Warehouse, OutDelivery, InwardReturned,OutwardReturned
    delivery_address = models.TextField()
    state = models.ForeignKey("setup.NigState", default=1, on_delete=models.DO_NOTHING,related_name="order_state_items")
    lga = models.ForeignKey("setup.Lga", default=1,on_delete=models.DO_NOTHING,related_name="order_lga_items")
    zone = models.ForeignKey("setup.Zone", default=1, on_delete=models.DO_NOTHING,related_name="zone_order_items")
    weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    worth = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sender_name = models.CharField(max_length=255)
    sender_phone = models.CharField(max_length=20,null=True)
    sender_email = models.CharField(max_length=50,null=True)
    receiver_name=models.CharField(max_length=100, null=True)
    receiver_phone = models.CharField(max_length=20,null=True)
    receiver_email = models.CharField(max_length=50,null=True)
    receiver_alt_phone = models.CharField(max_length=20,null=True)
    waybillNo = models.CharField(max_length=150, null=True,blank=True)
    delivery_otp = models.CharField(max_length=150, null=True,blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    holding_period = models.IntegerField(default=24)

    source = models.CharField(
        max_length=20,
        choices=[
            ('API', 'API'),
            ('UPLOAD', 'Upload'),
            ('MANUAL', 'Manual'),
        ],
        default='MANUAL'
    )
    
    def __str__(self):
        return self.barcode
    
class WarehouseScan(models.Model):
    item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name='warehouse_scan')
    time_in = models.DateTimeField(auto_now_add=True)
    time_out = models.DateTimeField(null=True, blank=True)
    flag = models.CharField(max_length=100, default="IN_WAREHOUSE")
    createdBy = models.ForeignKey("setup.User",on_delete=models.SET_NULL,null=True,related_name="warehouse_created"
)
    created_at = models.DateTimeField(auto_now_add=True)
    updatedBy =  models.CharField(max_length=100,null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    lastUpdatedat = models.DateTimeField(auto_created=True,null=True)
    
    def is_over_24hrs(self):
        if self.time_out:
            return False
        return timezone.now() > self.time_in + timedelta(hours=self.item.holding_period)
    
class Meta:
    indexes = [
        models.Index(fields=['barcode']),
        models.Index(fields=['flag']),
    ]

class LogisticsPartner(models.Model):
    name = models.CharField(max_length=100)#company name
    contact = models.CharField(max_length=100)  # name of contact person
    regno = models.CharField(max_length=50,null=True,blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.CharField(max_length=200, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    createdBy = models.ForeignKey( "setup.User",on_delete=models.CASCADE, related_name="added_partner")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    

class Vehicle(models.Model):
    vehicleTag = models.CharField(max_length=100, unique=True)
    vehicleType = models.CharField(max_length=100)
    vehicleNo = models.CharField(max_length=100)
    vehicleModel = models.CharField(max_length=100)
    vehicleYear = models.IntegerField(null=True, blank=True)
    vehicleWeight = models.IntegerField(null=True, blank=True)
    papersExpiryDate = models.DateField(null=True, blank=True)

    # ✅ NEW: Ownership
    OWNER_TYPE_CHOICES = [
        ('Company', 'Company'),
        ('Partner', 'Logistics Partner'),
    ]

    owner_type = models.CharField(
        max_length=20,
        choices=OWNER_TYPE_CHOICES,
        default='Company'
    )

    logistics_partner = models.ForeignKey(
        LogisticsPartner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicles'
    )

    AVAILABLE = 'Available'
    IN_USE = 'In Use'
    MAINTENANCE = 'Maintenance'

    STATUS_CHOICES = [
        (AVAILABLE, 'Available'),
        (IN_USE, 'In Use'),
        (MAINTENANCE, 'Maintenance'),
    ]

    vehicleStatus = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=AVAILABLE
    )

    createdBy = models.ForeignKey(
        "setup.User",
        on_delete=models.DO_NOTHING,
        related_name="added_vehicle"
    )

    createdAt = models.DateTimeField(auto_now_add=True)

    def clean(self):
        # ✅ Ensure consistency
        if self.owner_type == 'Partner' and not self.logistics_partner:
            raise ValidationError("Partner vehicle must have a logistics partner.")

        if self.owner_type == 'Company' and self.logistics_partner:
            raise ValidationError("Company vehicle should not have a logistics partner.")

    def __str__(self):
        owner = self.logistics_partner.name if self.logistics_partner else "Company"
        return f"{self.vehicleTag} - {self.vehicleNo} ({owner})"


from django.core.exceptions import ValidationError
from django.utils import timezone

class DispatchStatus:
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    PARTIAL = "PARTIAL"
    RETURNED = "RETURNED"
    ISSUE = "ISSUE"

    CHOICES = [
        (ASSIGNED, "Assigned"),
        (PICKED_UP, "Picked Up"),
        (IN_TRANSIT, "In Transit"),
        (DELIVERED, "Delivered"),
        (PARTIAL, "Partial"),
        (RETURNED, "Returned"),
        (ISSUE, "Issue"),
    ]

class Dispatch(models.Model):
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="dispatch"
    )
    batch_no=models.CharField(max_length=30,null=True,blank=True)
    agent = models.ForeignKey(
        "setup.User",
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'Dispatcher'}
    )

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # 🔹 STATUS
    status = models.CharField(
        max_length=20,
        choices=DispatchStatus.CHOICES,
        default=DispatchStatus.ASSIGNED
    )

    # 🔹 ASSIGNMENT
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        "setup.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="assigned_dispatches"
    )

    # 🔹 PICKUP (Warehouse → Dispatcher)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    picked_up_by = models.ForeignKey(
        "setup.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="picked_dispatches"
    )

    # 🔹 DELIVERY
    delivered_at = models.DateTimeField(null=True, blank=True)

    # 🔹 EXCEPTION HANDLING
    issue_reason = models.TextField(null=True, blank=True)

    # 🔹 TRACK REASSIGNMENT
    reassigned_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.agent.role != 'Dispatcher':
            raise ValidationError("Assigned user must be a dispatcher")

        # Enforce reason for exception statuses
        if self.status in ["PARTIAL", "RETURNED", "ISSUE"] and not self.issue_reason:
            raise ValidationError("Reason is required for this status")

    def __str__(self):
        return f"{self.order_item.barcode}"
    
class DispatchHistory(models.Model):
    dispatch = models.ForeignKey(Dispatch, on_delete=models.CASCADE, related_name="history")

    old_agent = models.ForeignKey("setup.User", on_delete=models.SET_NULL, null=True, related_name="+")
    new_agent = models.ForeignKey("setup.User", on_delete=models.SET_NULL, null=True, related_name="+")

    old_vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, related_name="+")
    new_vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, related_name="+")

    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey("setup.User", on_delete=models.SET_NULL, null=True)

class AgentLocation(models.Model):
    agent = models.ForeignKey("setup.User", on_delete=models.CASCADE)
    barcode = models.CharField(max_length=100, null=True, blank=True)  # optional link to delivery
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy = models.FloatField(null=True, blank=True)  # GPS accuracy (important!)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.agent} - {self.latitude},{self.longitude} @ {self.timestamp}"


class DeliveryAlert(models.Model):
    ALERT_TYPES = [
        ("DEVIATION", "Route Deviation"),
        ("DELAY", "Delivery Delay"),
        ("STOPPED", "Agent Stopped"),
        ("ISSUE", "Delivery Issue"),
    ]

    agent = models.ForeignKey("setup.User", on_delete=models.CASCADE)
    barcode = models.CharField(max_length=100)  # ❌ removed unique=True
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    message = models.TextField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.alert_type} - {self.barcode}"


class driverpickup(models.Model):
    agent = models.ForeignKey("setup.User", on_delete=models.CASCADE)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    batch_no=models.CharField(max_length=30,null=True,blank=True)
    flag=models.CharField(max_length=30,default="Pending",null=True,blank=True)
    created_by = models.ForeignKey("setup.User", on_delete=models.CASCADE,related_name="created_batch")
    created_at = models.DateTimeField(auto_now_add=True)
    action_done = models.CharField(max_length=30,default="Dispatched",null=True,blank=True)
    dispatch_hub = models.ForeignKey("hub",on_delete=models.SET_NULL,related_name="dispatch_hub", null=True,blank=True)
    
    def __str__(self):
        return f"{self.batch_no}"


class Hub(models.Model):
  hubName=models.CharField(max_length=100)
  hubAdd=models.CharField(max_length=200,null=True)
  city=models.CharField(max_length=200,null=True)
  hubState = models.ForeignKey("setup.NigState",on_delete=models.DO_NOTHING,related_name="hub_state")
  hubStatus=models.CharField(max_length=200,default='Active')
  createdBy=models.ForeignKey("setup.User",models.DO_NOTHING,related_name="hub_created_by")
  createdAt=models.DateTimeField(auto_created=True)
  
  # def __str__(self):
  #       return self.hubName
  def __str__(self):
        return self.hubName  # ✅ Ensure it returns a string
    
  class Meta:
        db_table = "hubs"


class HubTransfer(models.Model):
    batch_no = models.ForeignKey("driverpickup", on_delete=models.CASCADE,related_name="transfer_batch_no")
    srchub = models.ForeignKey("hub",on_delete=models.DO_NOTHING,related_name="transfer_src")   # warehouse or hub
    desthub = models.ForeignKey("hub",on_delete=models.DO_NOTHING,related_name="transfer_dest")   # hub
    status = models.CharField(max_length=250,default="Pending")  # pending, in_transit, arrived, dispatched
    created_by = models.ForeignKey("setup.User",models.DO_NOTHING,related_name="transfer_created_by")
    created_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(null=True,blank=True)

    def __str__(self):
        return self.batch_no  # ✅ Ensure it returns a string
    
   
    
    class Meta:
        db_table = "hubtransfers"
    

class HubTransferItem(models.Model):
    transfer = models.ForeignKey(HubTransfer, on_delete=models.DO_NOTHING, related_name="items")
    barcode = models.CharField(max_length=50,null=True,blank=True)
    weight = models.DecimalField(max_digits=10,decimal_places=2)
    flag = models.CharField(max_length=50,null=True,blank=True)

    def __str__(self):
        return f"{self.barcode}"
    
    class Meta:
        db_table ="hubtransferitems"

class HubScan(models.Model):
    transfer_item = models.ForeignKey(HubTransferItem,on_delete=models.DO_NOTHING)
    scanned_by = models.ForeignKey("setup.User",on_delete=models.DO_NOTHING,related_name="hubscan_scanned_by")
    flag = models.CharField(max_length=50, blank=True, null=True)  
    agent = models.ForeignKey("setup.User",on_delete=models.CASCADE,limit_choices_to={'role': 'Dispatcher'},null=True, blank=True,related_name="hubscan_agent")
    vehicle = models.ForeignKey(Vehicle,on_delete=models.SET_NULL,null=True,blank=True)
    created_at = models.DateTimeField(auto_created=True)
    def __str__(self):
        return self.flag
    
    class Meta:
        db_table ="hubscan"