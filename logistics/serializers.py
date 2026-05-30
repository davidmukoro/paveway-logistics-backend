from datetime import timedelta

from rest_framework import serializers
from setup.utils import generate_staffNo
from .utils import create_tracking, generate_waybill_no, geocode_address
from .models import (
    Order,
    OrderItem,
    WarehouseScan,
    Vehicle,
    Dispatch,
    LogisticsPartner,
    driverpickup,
    Hub,
    HubTransfer,
    HubTransferItem,
    OrderItemTracking,
)
from django.db import transaction
from setup.models import User
from django.db import transaction
from django.utils import timezone
from setup.models import Zone, Lga, NigState


class OrderItemTrackingSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.CharField(
        source="updated_by.fullName", read_only=True
    )

    class Meta:
        model = OrderItemTracking
        fields = "__all__"
        read_only_fields = ["updated_by", "updated_at"]


class WayBillHistorySerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)
    lga_name = serializers.CharField(source="lga.name", read_only=True)
    zone_name = serializers.CharField(source="zone.name", read_only=True)
    batch_no = serializers.CharField(source="order.order_no", read_only=True)

    class Meta:
        model = OrderItem
        exclude = ["order"]  # 🔥 IMPORTANT


class OrderItemSerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)
    lga_name = serializers.CharField(source="lga.name", read_only=True)
    zone_name = serializers.CharField(source="zone.name", read_only=True)

    class Meta:
        model = OrderItem
        exclude = ["order"]  # 🔥 IMPORTANT

    def validate_barcode(self, value):
        if OrderItem.objects.filter(barcode=value).exists():
            raise serializers.ValidationError("Barcode already exists")
        return value


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    vendor_name = serializers.CharField(source="vendor.fullName", read_only=True)
    createdBy_name = serializers.CharField(source="createdBy.fullName", read_only=True)

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ["createdBy"]
        extra_kwargs = {
            "lga": {"required": False},
            "zone": {"required": False},
        }

    def validate(self, data):
        if not data.get("items"):
            raise serializers.ValidationError("At least one item is required")
        return data

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        source = self.context.get("source", "MANUAL")
        daddress = validated_data.get("delivery_address")
        # lat, lng = geocode_address(daddress)
        order = Order.objects.create(**validated_data)

        # order_items = []

        # for item in items_data:
        #     item_source = item.pop("source", source)
        #     item_address = item.pop("delivery_address", daddress)
        #     zone = item.pop("zone", None)
        #     lga = item.pop("lga", None)
        #     state = item.pop("state", None)

        #     item["zone_id"] = zone.id if zone else None
        #     item["lga_id"] = lga.id if lga else None
        #     item["state_id"] = state.id if state else None

        #     zone_name = zone.name if zone else ""
        #     lga_name = lga.name if lga else ""
        #     state_name = state.name if state else ""

        #     lat, lng = (None, None)

        #     if item_address and item_address.strip():

        #         full_address = (
        #             f"{item_address}, {zone_name}, {lga_name}, {state_name}, Nigeria"
        #         )
        #         lat, lng = geocode_address(full_address.strip())

        #     # CREATE INITIAL TRACKING
        #     create_tracking(
        #         order_item=item,
        #         stage="CREATED",
        #         user=self.context["request"].user,
        #         remark="Shipment created",
        #     )

        #     order_items.append(
        #         OrderItem(
        #             order=order,
        #             source=item_source,
        #             delivery_address=item_address,
        #             flag="PENDING",
        #             latitude=lat,
        #             longitude=lng,
        #             **item,
        #         )
        #     )

        # OrderItem.objects.bulk_create(order_items)
        for item in items_data:

            item_source = item.pop("source", source)
            item_address = item.pop("delivery_address", daddress)

            zone = item.pop("zone", None)
            lga = item.pop("lga", None)
            state = item.pop("state", None)

            item["zone_id"] = zone.id if zone else None
            item["lga_id"] = lga.id if lga else None
            item["state_id"] = state.id if state else None

            zone_name = zone.name if zone else ""
            lga_name = lga.name if lga else ""
            state_name = state.name if state else ""

            lat, lng = (None, None)

            if item_address and item_address.strip():

                full_address = (
                    f"{item_address}, {zone_name}, "
                    f"{lga_name}, {state_name}, Nigeria"
                )

                lat, lng = geocode_address(full_address.strip())

            # SAVE ORDER ITEM
            order_item = OrderItem.objects.create(
                order=order,
                source=item_source,
                delivery_address=item_address,
                flag="PENDING",
                latitude=lat,
                longitude=lng,
                **item,
            )

            # CREATE TRACKING
            create_tracking(
                order_item=order_item,
                stage="CREATED",
                user=self.context["request"].user,
                remark="Shipment created",
            )

        return order


class WarehouseScanSerializer(serializers.ModelSerializer):
    barcode = serializers.CharField(source="item.barcode", read_only=True)
    receiver = serializers.CharField(source="item.receiver_name", read_only=True)
    phone = serializers.CharField(source="item.receiver_phone", read_only=True)
    address = serializers.CharField(source="item.delivery_address", read_only=True)

    state = serializers.CharField(source="item.state.name", read_only=True)
    lga = serializers.CharField(source="item.lga.name", read_only=True)
    zone = serializers.CharField(source="item.zone.name", read_only=True)
    weight = serializers.CharField(source="item.weight", read_only=True)

    vendor = serializers.CharField(source="item.order.vendor.fullName", read_only=True)
    overdue = serializers.SerializerMethodField(read_only=True)
    holding_period = serializers.IntegerField(
        source="item.holding_period", read_only=True
    )

    class Meta:
        model = WarehouseScan
        fields = [
            "item_id",
            "barcode",
            "vendor",
            "receiver",
            "phone",
            "address",
            "state",
            "lga",
            "zone",
            "time_in",
            "flag",
            "overdue",
            "weight",
            "holding_period",
        ]
        extra_kwargs = {"holding_period": {"required": False}}

    def get_overdue(self, obj):
        return obj.is_over_24hrs()


class DispatcherSerializer(serializers.ModelSerializer):
    fullName = serializers.SerializerMethodField()
    logistics_partner_name = serializers.SerializerMethodField()
    # assigned_vehicle = serializers.CharField(source="agent.assignedVehicle",read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "fullName",
            "dispatcher_type",
            "dispatcher_flag",
            "date_joined",
            "mobileNo",
            "staffNo",
            "date_joined",
            "logistics_partner_name",
            "assignedVehicle",
        ]

        read_only_fields = ("assigedVehicle",)

    def get_fullName(self, obj):
        return obj.get_user_fullname or obj.username

    def get_logistics_partner_name(self, obj):
        if obj.partner:
            return obj.partner.name
        return None  #

    def get_assignedVehicle(self, obj):
        return User.objects.get(id=obj.agent).assignedVehicle


class VehicleSerializer(serializers.ModelSerializer):
    createdBy_name = serializers.CharField(source="createdBy.fullName", read_only=True)
    logistics_partner_name = serializers.CharField(
        source="logistics_partner.name", read_only=True
    )

    class Meta:
        model = Vehicle
        fields = "__all__"
        read_only_fields = ["createdBy", "createdAt"]

    def get_logistics_partner_name(self, obj):
        if obj.logistics_partner:
            return obj.logistics_partner.name
        return None  # ✅ Always return something

    def validate(self, data):
        owner_type = data.get("owner_type", getattr(self.instance, "owner_type", None))
        logistics_partner = data.get(
            "logistics_partner", getattr(self.instance, "logistics_partner", None)
        )

        if owner_type == "Partner" and not logistics_partner:
            raise serializers.ValidationError(
                {"logistics_partner": "This field is required for partner vehicles."}
            )

        if owner_type == "Company" and logistics_partner:
            raise serializers.ValidationError(
                {
                    "logistics_partner": "Company vehicles should not have a logistics partner."
                }
            )

        return data


class BulkDispatchSerializer(serializers.Serializer):
    barcodes = serializers.ListField(child=serializers.CharField())
    agent_id = serializers.UUIDField()
    vehicle_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        agent_id = data.get("agent_id")
        vehicle_id = data.get("vehicle_id")
        barcodes = data.get("barcodes")

        # ✅ Validate dispatcher
        try:
            agent = User.objects.get(id=agent_id, role="Dispatcher")
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid dispatcher")

        # ✅ Validate vehicle
        vehicle = None
        if vehicle_id:
            try:
                vehicle = Vehicle.objects.get(id=vehicle_id)
                if vehicle.vehicleStatus != "Available":
                    raise serializers.ValidationError("Vehicle not available")
            except Vehicle.DoesNotExist:
                raise serializers.ValidationError("Vehicle not found")

        # ✅ Validate barcodes
        items = OrderItem.objects.filter(barcode__in=barcodes)

        if items.count() != len(barcodes):
            raise serializers.ValidationError("Some barcodes are invalid")

        # Optional: prevent re-dispatch
        # already_dispatched = Dispatch.objects.filter(barcode__in=barcodes)
        # if already_dispatched.exists():
        #     raise serializers.ValidationError("Some items already dispatched")
        already_dispatched = OrderItem.objects.filter(
            barcode__in=barcodes, flag="OUT_FOR_DELIVERY"
        )

        if already_dispatched.exists():
            raise serializers.ValidationError("Some items already dispatched")

        data["agent"] = agent
        data["vehicle"] = vehicle
        data["items"] = items

        return data

    @transaction.atomic
    def create(self, validated_data):
        agent = validated_data["agent"]
        vehicle = validated_data["vehicle"]
        items = validated_data["items"]

        dispatch_list = []

        for item in items:

            # ✅ Prevent re-dispatch via status (more reliable)
            if item.flag == "OUT_FOR_DELIVERY":
                continue

            # ✅ CREATE DISPATCH
            dispatch = Dispatch.objects.create(
                barcode=item.barcode,
                agent=agent,
                vehicle=vehicle,
                status="OUT_FOR_DELIVERY",
            )

            # ✅ UPDATE ORDER ITEM
            item.flag = "OUT_FOR_DELIVERY"
            item.save()

            # ✅ UPDATE WAREHOUSE EXIT
            scan = getattr(item, "warehouse_scan", None)
            if scan and not scan.time_out:
                scan.time_out = timezone.now()
                scan.flag = "OUT"
                scan.save()

            dispatch_list.append(dispatch)

        # ✅ UPDATE VEHICLE STATUS (ONLY IF USED)
        if vehicle and dispatch_list:
            vehicle.vehicleStatus = "In Use"
            vehicle.save()

        return dispatch_list


class PartnerSerializer(serializers.ModelSerializer):
    createdBy_name = serializers.CharField(source="createdBy.fullName", read_only=True)

    class Meta:
        model = LogisticsPartner
        # fields = ['id', 'vehicleTag', 'vehicleNo', 'vehicleType']
        fields = "__all__"


class DriverpickupSerializer(serializers.ModelSerializer):
    dispatch_hub = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.all(), required=False, allow_null=True
    )

    hub_name = serializers.CharField(source="dispatch_hub.hubName", read_only=True)

    agent_name = serializers.CharField(source="agent.fullName", read_only=True)
    vehicle_no = serializers.CharField(source="vehicle.vehicleNo", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.fullName", read_only=True
    )
    vehicleWeight = serializers.CharField(
        source="vehicle.vehicleWeight", read_only=True
    )
    assignedVehicle = serializers.CharField(
        source="agent.assignedVehicle", read_only=True
    )
    total_items = serializers.SerializerMethodField()

    class Meta:
        model = driverpickup
        fields = [
            "id",
            "batch_no",
            "flag",
            "agent",
            "agent_name",
            "vehicle",
            "vehicle_no",
            "created_by",
            "created_by_name",
            "created_at",
            "total_items",
            "vehicleWeight",
            "assignedVehicle",
            "action_done",
            "dispatch_hub",
            "hub_name",
        ]

        read_only_fields = (
            "batch_no",
            "vehicleWeight",
            "assignedVehicle",
            "hub_name",
        )

    def create(self, validated_data):  # generate batch number
        batch_no = generate_staffNo("PWBN", "batchno")
        validated_data["batch_no"] = batch_no
        validated_data["created_at"] = timezone.now()
        return driverpickup.objects.create(**validated_data)

    def get_total_items(self, obj):
        return Dispatch.objects.filter(batch_no=obj.batch_no).count()


class DispatchSerializer(serializers.ModelSerializer):
    barcode = serializers.CharField(source="order_item.barcode")
    vehicleNo = serializers.CharField(source="vehicle.vehicleNo", default=None)
    receiver = serializers.CharField(source="order_item.receiver_name", read_only=True)
    address = serializers.CharField(
        source="order_item.delivery_address", read_only=True
    )
    phone = serializers.CharField(source="order_item.receiver_phone", read_only=True)
    waybill = serializers.CharField(source="order_item.waybillNo", read_only=True)
    weight = serializers.CharField(source="order_item.weight", read_only=True)
    agent = serializers.CharField(source="agent.get_user_fullname", read_only=True)

    class Meta:
        model = Dispatch
        fields = [
            "id",
            "barcode",
            "vehicleNo",
            "receiver",
            "address",
            "phone",
            "waybill",
            "status",
            "assigned_at",
            "weight",
            "agent",
            "batch_no",
            "delivered_at",
        ]
        extra_kwargs = {
            "delivered_at": {"required": False},
        }


class HubSerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="hubState.name", read_only=True)
    createdBy_name = serializers.CharField(source="createdBy.fullName", read_only=True)

    class Meta:
        model = Hub
        fields = [
            "id",
            "hubName",
            "hubAdd",
            "hubState",
            "city",
            "hubStatus",
            "createdBy",
            "createdBy_name",
            "state_name",
            "createdAt",
        ]
        extra_kwargs = {
            "createdAt": {"required": False},
            "createdBy_name": {"required": False},
        }


class HubTransferItemSerializer(serializers.ModelSerializer):

    class Meta:
        model = HubTransferItem
        fields = ["id", "barcode", "weight"]

        def validate(self, data):
            if data["srchub"] == data["desthub"]:
                raise serializers.ValidationError(
                    "Source and destination hub cannot be the same."
                )
            return data


class HubTransferSerializer(serializers.ModelSerializer):
    items = HubTransferItemSerializer(many=True)
    srch = serializers.CharField(source="srchub.hubName", read_only=True)
    desth = serializers.CharField(source="desthub.hubName", read_only=True)
    createdBy_user = serializers.CharField(source="created_by.fullName", read_only=True)
    batchNo = serializers.CharField(source="batch_no.batch_no", read_only=True)
    total_items = serializers.SerializerMethodField()

    class Meta:
        model = HubTransfer
        fields = [
            "id",
            "batch_no",
            "srchub",
            "desthub",
            "status",
            "created_by",
            "created_at",
            "items",
            "srch",
            "desth",
            "createdBy_user",
            "batchNo",
            "total_items",
            "comment",
        ]
        read_only_fields = [
            "created_at",
            "srch",
            "desth",
            "createdBy_user",
            "batchNo",
            "total_items",
        ]

    def get_total_items(self, obj):
        return HubTransferItem.objects.filter(transfer_id=obj.id).count()

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        items_data = validated_data.pop("items")

        agent_id = request.data.get("agent_id")
        vehicle_id = request.data.get("vehicle_id")

        agent = User.objects.get(pk=agent_id)
        vehicle = Vehicle.objects.get(pk=vehicle_id)

        transfer = HubTransfer.objects.create(**validated_data)

        dpup = driverpickup.objects.get(batch_no=str(transfer.batch_no.batch_no))
        dpup.action_done = "Transferred"
        dpup.flag = "Completed"
        dpup.save()

        barcodes = []

        for item_data in items_data:
            barcode = item_data.get("barcode")

            HubTransferItem.objects.create(transfer=transfer, **item_data)
            create_tracking(
                order_item=item_data,
                stage="HUB_TRANSFER",
                user=request.user,
                remark="Item Transferred to Hub",
            )
            if barcode:
                barcodes.append(barcode)

        # ===============================
        # 🔥 FETCH ORDER ITEMS (LOCKED)
        # ===============================
        items = OrderItem.objects.select_for_update().filter(barcode__in=barcodes)

        if items.count() != len(barcodes):
            raise serializers.ValidationError("Some items not found")

        # ===============================
        # 🔥 PROCESS ITEMS
        # ===============================
        for item in items:

            # 🚫 Must be in warehouse
            if item.flag != "WAREHOUSE":
                raise serializers.ValidationError(
                    f"Item {item.barcode} is not in warehouse"
                )

            # ===============================
            # ✅ CLOSE WAREHOUSE SCAN
            # ===============================
            scan = getattr(item, "warehouse_scan", None)
            if scan and not scan.time_out:
                scan.time_out = timezone.now()
                scan.updatedBy = request.user.fullName
                scan.flag = "IN_HUB_TRANSFER"
                scan.save()

            # ===============================
            # ✅ UPDATE ITEM STATE
            # ===============================
            item.flag = "IN_HUB_TRANSFER"

            if not item.waybillNo:
                item.waybillNo = generate_waybill_no(
                    item.state.code if item.state else "XXX"
                )

            item.save()

            # ===============================
            # ✅ CREATE / UPDATE DISPATCH
            # ===============================
            dispatch, created = Dispatch.objects.get_or_create(
                order_item=item,
                defaults={
                    "agent": agent,  # or None if not yet assigned
                    "vehicle": vehicle,
                    "status": "IN_HUB_TRANSFER",
                    "assigned_by": request.user,
                    "assigned_at": timezone.now(),
                    "batch_no": str(transfer.batch_no.batch_no),  # 👈 string batch
                },
            )

            if not created:
                # Optional: update existing dispatch if needed
                dispatch.status = "IN_HUB_TRANSFER"
                dispatch.assigned_by = request.user
                dispatch.batch_no = str(transfer.batch_no.batch_no)
                dispatch.save()

        return transfer

    from django.db import transaction

    @transaction.atomic  # At Hub
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)

        # Update main transfer fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # =====================================================
        # 1. If transfer status = Received
        #    Update existing HubTransferItem -> flag = WAREHOUSE
        # =====================================================
        if instance.status == "Received":
            HubTransferItem.objects.filter(transfer=instance).update(flag="WAREHOUSE")
        create_tracking(
            order_item=item,
            stage="ARRIVED HUB WAREHOUSE",
            user=instance["request"].user,
            remark="Item Received at the Hub",
        )
        # =====================================================
        # 2. If frontend sends items again
        #    Recreate items + update OrderItem + HubTransferItem
        # =====================================================
        if items_data is not None:
            # delete old items first
            instance.items.all().delete()

            barcodes = []

            for item in items_data:
                barcode = item.get("barcode")

                # create new HubTransferItem
                created_item = HubTransferItem.objects.create(transfer=instance, **item)

                # if transfer already marked received,
                # ensure new item also gets WAREHOUSE
                if instance.status == "Received":
                    created_item.flag = "WAREHOUSE"
                    created_item.save()

                if barcode:
                    barcodes.append(barcode)

            # =================================================
            # Update OrderItem flag -> PICKUP
            # =================================================
            if barcodes:
                OrderItem.objects.filter(barcode__in=barcodes).update(flag="PICKUP")

        return instance


class HubStoreSerializer(serializers.ModelSerializer):
    receiver_name = serializers.CharField(read_only=True)
    delivery_address = serializers.CharField(read_only=True)
    waybillNo = serializers.CharField(read_only=True)
    batch_no = serializers.CharField(read_only=True)
    holding_period = serializers.CharField(read_only=True)
    flag = serializers.CharField(read_only=True)
    hub_name = serializers.CharField(source="transfer.desthub.hubName", read_only=True)

    class Meta:
        model = HubTransferItem
        fields = [
            "id",
            "barcode",
            "weight",
            "receiver_name",
            "delivery_address",
            "waybillNo",
            "batch_no",
            "holding_period",
            "flag",
            "hub_name",
        ]


class WarehouseHoldingReportSerializer(serializers.ModelSerializer):
    barcode = serializers.CharField(source="item.barcode")
    description = serializers.CharField(source="item.description")
    sender_name = serializers.CharField(source="item.sender_name")
    receiver_name = serializers.CharField(source="item.receiver_name")
    receiver_phone = serializers.CharField(source="item.receiver_phone")
    delivery_address = serializers.CharField(source="item.delivery_address")
    state = serializers.CharField(source="item.state.name")
    lga = serializers.SerializerMethodField()
    holding_period = serializers.IntegerField(source="item.holding_period")
    hours_in_warehouse = serializers.SerializerMethodField()
    exceeded_by_hours = serializers.SerializerMethodField()
    orderNo = serializers.CharField(source="item.order.order_no")
    vendor_name = serializers.CharField(source="item.order.vendor.fullName")
    worth = serializers.DecimalField(
        source="item.worth",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = WarehouseScan
        fields = [
            "id",
            "barcode",
            "description",
            "sender_name",
            "receiver_name",
            "receiver_phone",
            "delivery_address",
            "state",
            "lga",
            "orderNo",
            "worth",
            "time_in",
            "holding_period",
            "hours_in_warehouse",
            "exceeded_by_hours",
            "flag",
            "vendor_name",
        ]

    def get_lga(self, obj):
        return obj.item.lga.name if obj.item.lga else ""

    def get_hours_in_warehouse(self, obj):
        diff = timezone.now() - obj.time_in
        return round(diff.total_seconds() / 3600, 1)

    def get_exceeded_by_hours(self, obj):
        diff = timezone.now() - obj.time_in
        total_hours = diff.total_seconds() / 3600
        exceeded = total_hours - obj.item.holding_period
        return round(max(exceeded, 0), 1)


from rest_framework import serializers
from django.utils import timezone
from .models import OrderItem


class PendingWarehouseScanReportSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_no", read_only=True)

    customer_name = serializers.CharField(
        source="order.vendor.fullName",
        read_only=True,
    )

    customer_phone = serializers.CharField(
        source="order.vendor.mobileNo",
        read_only=True,
    )

    waiting_days = serializers.SerializerMethodField()
    waiting_duration = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "barcode",
            "description",
            "order_number",
            "customer_name",
            "customer_phone",
            "qty",
            "flag",
            "sender_name",
            "sender_phone",
            "receiver_name",
            "receiver_phone",
            "delivery_address",
            "waybillNo",
            "scanned_at",
            "waiting_days",
            "waiting_duration",
        ]

    def get_waiting_days(self, obj):
        if obj.scanned_at:
            diff = timezone.now() - obj.scanned_at
            return diff.days
        return 0

    def get_waiting_duration(self, obj):
        if not obj.scanned_at:
            return "N/A"

        diff = timezone.now() - obj.scanned_at

        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        parts = []

        if days > 0:
            parts.append(f"{days} day{'s' if days > 1 else ''}")

        if hours > 0:
            parts.append(f"{hours} hr{'s' if hours > 1 else ''}")

        if minutes > 0:
            parts.append(f"{minutes} min{'s' if minutes > 1 else ''}")

        return " ".join(parts) if parts else "Just now"
