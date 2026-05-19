from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from finance.utils import compute_customer_wallet_balance
from setup.utils import AuditedModelViewSet
from .services.vendor_service import fetch_vendor_orders
from django.db.models import Q
from .models import (
    DispatchHistory,
    HubTransfer,
    Order,
    OrderItem,
    WarehouseScan,
    LogisticsPartner,
    driverpickup,
    Hub,
    AgentLocation,
    HubTransferItem,
    HubScan,
    OrderItemTracking,
)
from .serializers import (
    BulkDispatchSerializer,
    OrderItemSerializer,
    OrderSerializer,
    WarehouseScanSerializer,
    HubSerializer,
    PartnerSerializer,
    DispatchSerializer,
    DriverpickupSerializer,
    HubTransferSerializer,
    HubStoreSerializer,
    WayBillHistorySerializer,
    OrderItemTrackingSerializer,
)
from django.utils import timezone
from .utils import (
    create_tracking,
    generate_delivery_code,
    generate_waybill_no,
    normalize_vendor_payload,
)
from setup.models import User
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
import pandas as pd
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import VehicleSerializer, DispatcherSerializer
from finance.models import WalletFunding

# from rest_framework.views import APIView
from django.utils import timezone
from logistics.models import Dispatch, Vehicle
from setup.models import User
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from rest_framework.response import Response
from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q, OuterRef, Subquery
from collections import defaultdict
from rest_framework import status as http_status
from django.http import JsonResponse
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework import status


class WaybillHistory(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # If staff → return all orders
        if user.is_staff:
            orders = Order.objects.all()
        else:
            # Non-staff → return only user's orders
            orders = Order.objects.filter(vendor_id=user.id)

        orders = OrderItem.objects.select_related("order").order_by("-order_id")

        serializer = WayBillHistorySerializer(orders, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderItemTrackingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrderItemTrackingSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(updated_by=request.user)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, search):

        tracking = (
            OrderItemTracking.objects.select_related("order_item", "updated_by")
            .filter(
                Q(order_item__barcode__iexact=search)
                | Q(order_item__waybillNo__iexact=search)
            )
            .order_by("-updated_at")
        )

        serializer = OrderItemTrackingSerializer(tracking, many=True)

        return Response(serializer.data)


class TrackWayBill(APIView):
    permission_classes = [AllowAny]

    def get(self, request, waybill):

        tracking = (
            OrderItemTracking.objects.select_related("order_item", "updated_by")
            .filter(
                Q(order_item__barcode__iexact=waybill)
                | Q(order_item__waybillNo__iexact=waybill)
            )
            .order_by("-updated_at")
        )

        serializer = OrderItemTrackingSerializer(tracking, many=True)

        return Response(serializer.data)


class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # If staff → return all orders
        if user.is_staff:
            orders = Order.objects.all()
        else:
            # Non-staff → return only user's orders (vendor_id = user.id)
            orders = Order.objects.filter(vendor_id=user.id)

        orders = orders.prefetch_related("items").order_by("-created_at")
        serializer = OrderSerializer(orders, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = OrderSerializer(
            data=request.data,
            context={"request": request, "source": request.data.get("source")},
        )

        if serializer.is_valid():
            order = serializer.save(createdBy=request.user)

            return Response(
                {"message": "Order created successfully", "order_id": str(order.id)},
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def create_order_with_wallet_deduction(request):
    try:
        data = request.data

        with transaction.atomic():

            # 1. Check Balance
            total_bill = float(data["totalBill"])
            customer_balance = compute_customer_wallet_balance(data["vendor"])
            # customer_balance = float(data["customerBalance"])

            if customer_balance < total_bill:
                return Response(
                    {"message": "Insufficient Balance"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 2. Deduct Wallet
            WalletFunding.objects.create(
                customer_id=data["vendor"],
                transactionDate=timezone.now(),
                txntype="Expense",
                amount=-total_bill,
                txnRef=data["vendor_order_no"],
                narration=f"Billing for {data['vendor_order_no']}",
                postedBy=request.user.fullName,
            )

            # 3. Create Order using existing serializer
            serializer = OrderSerializer(
                data=data,
                context={
                    "request": request,
                    "source": data.get("source"),
                },
            )

            if not serializer.is_valid():

                # Raising exception ensures rollback
                transaction.set_rollback(True)

                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST,
                )

            order = serializer.save(createdBy=request.user)

        return Response(
            {
                "message": "Order created successfully",
                "order_id": str(order.id),
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        return Response(
            {"message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class VendorFetchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vendor_id = request.GET.get("vendor_id")

        if not vendor_id:
            return Response({"error": "vendor_id is required"}, status=400)

        vendor = get_object_or_404(User, pk=vendor_id)
        try:
            external_data = fetch_vendor_orders(vendor)  # get_vendor_data(vendor)
            normalized = normalize_vendor_payload(external_data, vendor.id)
            return Response(normalized)
        except Exception as e:
            return Response(
                {"error": "Failed to fetch vendor data", "details": str(e)}, status=500
            )


class OrderUploadPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("file")
        vendor_id = request.data.get("vendor")

        if not file:
            return Response({"error": "No file uploaded"}, status=400)

        try:
            df = pd.read_excel(file)

            items = []
            errors = []

            for index, row in df.iterrows():
                try:
                    item = {
                        "barcode": str(row.get("barcode")),
                        "receiver_name": row.get("receiver_name"),
                        "receiver_phone": row.get("receiver_phone"),
                        "sender_name": row.get("sender_name"),
                        "sender_phone": row.get("sender_phone"),
                        "delivery_address": row.get("address"),
                        "state": row.get("state"),
                        "lga": row.get("lga"),
                        "zone": row.get("zone"),
                        "weight": row.get("weight"),
                        "worth": row.get("worth"),
                    }

                    # simple validation
                    if not item["barcode"]:
                        raise ValueError("Barcode is required")

                    items.append(item)

                except Exception as e:
                    errors.append({"row": index + 1, "error": str(e)})

            return Response(
                {
                    "vendor": vendor_id,
                    "vendor_order_no": f"UPLOAD-{vendor_id}",
                    "items": items,
                    "errors": errors,  # 🔥 RETURN ERRORS
                }
            )

        except Exception as e:
            return Response({"error": str(e)}, status=500)


class ScanItemView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        barcodes = request.data.get("barcodes", [])

        if not isinstance(barcodes, list):
            return Response({"error": "barcodes must be a list"}, status=400)

        scanned = []
        not_found = []

        for code in barcodes:
            try:
                item = OrderItem.objects.get(barcode=code)

                if not item.is_scanned:
                    item.is_scanned = True
                    item.scanned_at = timezone.now()
                    item.save()

                    WarehouseScan.objects.create(item=item)

                scanned.append(code)

            except OrderItem.DoesNotExist:
                not_found.append(code)

        return Response({"scanned": scanned, "not_found": not_found})


class OverdueItemsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        overdue = []

        scans = WarehouseScan.objects.all()

        for scan in scans:
            if scan.is_over_24hrs():
                overdue.append({"barcode": scan.item.barcode, "time_in": scan.time_in})

        return Response(overdue)


class UploadOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("file")

        df = pd.read_excel(file)

        for _, row in df.iterrows():
            order = Order.objects.create(
                vendor_id=row["vendor_id"],
                vendor_order_no=row["vendor_order_no"],
                customer_name=row["customer_name"],
                delivery_address=row["delivery_address"],
                lga=row["lga"],
                zone=row["zone"],
                weight=row.get("weight", 0),
                delivery_fee=row.get("delivery_fee", 0),
                source="UPLOAD",
            )

            OrderItem.objects.create(order=order, barcode=row["barcode"])

        return Response({"message": "Uploaded successfully"})


class WarehouseScanView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        barcode = request.data.get("barcode")

        if not barcode:
            return Response({"error": "Barcode is required"}, status=400)

        try:
            item = OrderItem.objects.get(barcode=barcode)

            # already scanned
            if hasattr(item, "warehouse_scan"):
                return Response(
                    {"error": "Item already scanned", "barcode": barcode}, status=400
                )

            # mark item
            item.is_scanned = True
            item.scanned_at = timezone.now()
            item.flag = "WAREHOUSE"
            # item.delivery_fee=0. calculate it and lookup pricing template.
            item.save()

            # update tracking
            create_tracking(
                order_item=item,
                stage="WAREHOUSE",
                user=request.user,
                remark="Item Scanned into Warehouse",
            )

            # create warehouse record
            scan = WarehouseScan.objects.create(item=item, createdBy=request.user)

            return Response(
                {
                    "message": "Item scanned successfully",
                    "item": {
                        "barcode": item.barcode,
                        "receiver": item.receiver_name,
                        "address": item.delivery_address,
                        "phone": item.receiver_phone,
                        "time_in": scan.time_in,
                    },
                },
                status=200,
            )

        except OrderItem.DoesNotExist:
            return Response({"error": "Invalid barcode"}, status=404)

    def get(self, request):
        scans = WarehouseScan.objects.select_related(
            "item",
            "item__order",
            "item__state",
            "item__lga",
            "item__zone",
        ).order_by("-time_in")

        serializer = WarehouseScanSerializer(scans, many=True)
        return Response(serializer.data)


class OverdueItemsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scans = WarehouseScan.objects.select_related("item")

        overdue = [scan for scan in scans if scan.is_over_24hrs()]

        data = [
            {
                "barcode": s.item.barcode,
                "receiver": s.item.receiver_name,
                "time_in": s.time_in,
            }
            for s in overdue
        ]

        return Response(data)


class DispatcherListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        available = request.query_params.get("available")

        dispatchers = User.objects.filter(role="Dispatcher")

        # Apply filter ONLY if query param is provided
        if available is not None:
            if available.lower() == "true":
                dispatchers = dispatchers.filter(dispatcher_flag="Available")
            elif available.lower() == "false":
                dispatchers = dispatchers.filter(dispatcher_flag="Unavailable")

        dispatchers = dispatchers.order_by("-date_joined")
        serializer = DispatcherSerializer(dispatchers, many=True)
        return Response(serializer.data)


class UpdateDispatcherStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            dispatcher = User.objects.get(pk=pk, role="Dispatcher")
        except User.DoesNotExist:
            return Response({"error": "Dispatcher not found"}, status=404)

        new_status = request.data.get("dispatcher_flag")

        if new_status not in ["Available", "Unavailable"]:
            return Response({"error": "Invalid status"}, status=400)

        dispatcher.dispatcher_flag = new_status
        dispatcher.save()

        return Response(
            {
                "message": "Dispatcher status updated successfully",
                "status": dispatcher.dispatcher_flag,
            },
            status=status.HTTP_200_OK,
        )


class VehicleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vehicles = Vehicle.objects.all()

        owner_type = request.query_params.get("owner_type")
        status_param = request.query_params.get("status")

        if owner_type:
            vehicles = vehicles.filter(owner_type=owner_type)

        if status_param:
            vehicles = vehicles.filter(vehicleStatus=status_param)

        vehicles = vehicles.order_by("-createdAt")

        serializer = VehicleSerializer(vehicles, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = VehicleSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(createdBy=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VehicleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Vehicle, pk=pk)

    def get(self, request, pk):
        vehicle = self.get_object(pk)
        serializer = VehicleSerializer(vehicle)
        return Response(serializer.data)

    def patch(self, request, pk):
        vehicle = self.get_object(pk)
        serializer = VehicleSerializer(vehicle, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        vehicle = self.get_object(pk)

        if vehicle.vehicleStatus == "In Use":
            return Response({"error": "Vehicle currently in use"}, status=400)

        vehicle.delete()
        return Response({"message": "Deleted successfully"}, status=204)


class BulkDispatchView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        item_ids = request.data.get("order_item", [])
        agent_id = request.data.get("agent_id")
        vehicle_id = request.data.get("vehicle_id")

        if not item_ids:
            return Response({"error": "No items selected"}, status=400)

        try:
            agent = User.objects.get(id=agent_id)
        except User.DoesNotExist:
            return Response({"error": "Invalid dispatcher"}, status=400)

        vehicle = None
        if vehicle_id:
            try:
                vehicle = Vehicle.objects.get(id=vehicle_id)
                vehicle.vehicleStatus = "In Use"
                vehicle.save()
            except Vehicle.DoesNotExist:
                return Response({"error": "Invalid vehicle"}, status=400)

        dispatched_items = []

        for item_id in item_ids:
            try:
                item = OrderItem.objects.select_for_update().get(id=item_id)
            except OrderItem.DoesNotExist:
                # ❌ FAIL entire transaction
                raise Exception(f"OrderItem {item_id} not found")

            # Prevent double dispatch
            if item.flag == "OUT_FOR_DELIVERY":
                raise Exception(f"Item {item_id} already dispatched")

            # ✅ CREATE DISPATCH
            Dispatch.objects.create(
                order_item=item,
                agent=agent,
                vehicle=vehicle,
                status="OUT_FOR_DELIVERY",
            )

            # ✅ UPDATE ORDER ITEM
            item.flag = "OUT_FOR_DELIVERY"
            item.waybillNo = generate_waybill_no(
                item.state.code if item.state else "XXX"
            )
            item.delivery_otp = generate_delivery_code()
            item.save()

            # ✅ WAREHOUSE EXIT
            scan = getattr(item, "warehouse_scan", None)
            if scan and not scan.time_out:
                scan.time_out = timezone.now()
                scan.updatedBy = request.user.fullName
                scan.updated_at = timezone.now()
                scan.lastUpdatedat = timezone.now()
                scan.flag = "OUT"
                scan.save()

            dispatched_items.append(str(item.id))

        return Response(
            {
                "message": "Dispatch successful",
                "dispatched": dispatched_items,
            },
            status=200,
        )


class SingleDispatchView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data.copy()
        data["barcodes"] = [data.get("order_item")]

        serializer = BulkDispatchSerializer(data=data)

        if serializer.is_valid():
            result = serializer.save()

            # ✅ Update vehicle status if provided
            vehicle_id = request.data.get("vehicle_id")
            if vehicle_id:
                try:
                    vehicle = Vehicle.objects.get(id=vehicle_id)
                    vehicle.vehicleStatus = "In Use"
                    vehicle.save()
                except Vehicle.DoesNotExist:
                    raise Exception("Invalid vehicle")

            # update the warehouse scan record if exists
            item = result["dispatched_items"][0]  # single item
            scan = getattr(item, "warehouse_scan", None)
            if scan and not scan.time_out:
                scan.time_out = timezone.now()
                scan.updatedBy = request.user.fullName
                scan.updated_at = timezone.now()
                scan.lastUpdatedat = timezone.now()
                scan.flag = "OUT"
                scan.save()

            return Response({"message": "Dispatched"}, status=201)

        return Response(serializer.errors, status=400)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated


class DriverPickupCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data.copy()

        # Optional: force created_by = logged-in user
        data["created_by"] = request.user.id

        serializer = DriverpickupSerializer(data=data)

        if serializer.is_valid():
            pickup = serializer.save()

            return Response(
                {
                    "message": "Batch created successfully",
                    "data": DriverpickupSerializer(pickup).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        # frontend can pass ?hub=2
        hub_id = request.query_params.get("hub")

        pickups = driverpickup.objects.select_related(
            "agent", "vehicle", "created_by", "dispatch_hub"
        ).all()

        # If hub is passed, filter by dispatch_hub
        if hub_id:
            pickups = pickups.filter(dispatch_hub_id=hub_id)

        pickups = pickups.order_by("-created_at")

        serializer = DriverpickupSerializer(pickups, many=True)

        return Response(serializer.data, status=200)


class HubItemDetailView(APIView):
    def get(self, request):
        user_hub = request.user.hub_name
        pickups = (
            HubTransfer.objects.filter(desthub=user_hub)
            .select_related("batch_no", "srchub", "desthub", "created_by")
            .all()
            .order_by("-created_at")
        )

        serializer = HubTransferSerializer(pickups, many=True)

        return Response(serializer.data, status=200)


class ManifestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_no):
        # 🔥 Get all dispatch records for the batch
        dispatches = Dispatch.objects.filter(batch_no=batch_no).select_related(
            "order_item", "agent", "vehicle"
        )

        # 🔥 Extract order items from dispatch
        # items = [d.order_item for d in dispatches]
        items = OrderItem.objects.filter(dispatch__batch_no=batch_no).select_related(
            "state", "lga", "zone"
        )

        # 🔥 Get pickup (batch header info)
        pickup = (
            driverpickup.objects.filter(batch_no=batch_no)
            .select_related("agent", "vehicle")
            .first()
        )

        return Response(
            {
                "batch": {
                    "batch_no": batch_no,
                    "agent_name": pickup.agent.fullName if pickup else "",
                    "vehicle_no": (
                        pickup.vehicle.vehicleNo if pickup and pickup.vehicle else ""
                    ),
                    "created_at": pickup.created_at if pickup else None,
                },
                "items": [
                    {
                        "barcode": i.barcode,
                        "receiver": i.receiver_name,
                        "phone": i.receiver_phone,
                        "address": i.delivery_address,
                        "state": i.state.name if i.state else "",
                        "lga": i.lga.name if i.lga else "",
                        "zone": i.zone.name if i.zone else "",
                        "weight": float(i.weight or 0),
                        "waybill": i.waybillNo,
                    }
                    for i in items
                ],
            }
        )


@api_view(["GET"])
def getDispatchInfo(request, batchno):
    if request.user.is_authenticated:
        try:
            pickup = driverpickup.objects.get(batch_no=batchno)
        except driverpickup.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = DriverpickupSerializer(pickup)
        return Response(serializer.data)
    else:
        return Response(status=status.HTTP_401_UNAUTHORIZED)


class DispatchSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        summary = (
            Dispatch.objects.values("batch_no", "agent__fullName", "vehicle__vehicleNo")
            .annotate(
                agent=F("agent__fullName"),
                vehicleNo=F("vehicle__vehicleNo"),
                total_items=Count("id"),
            )
            .order_by("-batch_no")
        )

        return Response(summary, status=200)


class DriverPickupUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def put(self, request, batch_no):
        agent_id = request.data.get("agent")
        vehicle_id = request.data.get("vehicle")

        pickup = get_object_or_404(driverpickup, batch_no=batch_no)

        # ✅ UPDATE DRIVERPICKUP
        if agent_id:
            pickup.agent_id = agent_id

        if vehicle_id:
            pickup.vehicle_id = vehicle_id
        else:
            pickup.vehicle = None

        pickup.save()

        # ✅ UPDATE DISPATCH TABLE
        dispatches = Dispatch.objects.filter(batch_no=batch_no)

        for d in dispatches:
            if agent_id:
                d.agent_id = agent_id
                d.picked_up_by_id = agent_id  # 👈 IMPORTANT

            if vehicle_id:
                d.vehicle_id = vehicle_id
            else:
                d.vehicle = None

            d.save()

        return Response({"message": "Batch updated successfully"}, status=200)


class dispatcherPickupView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        barcodes = request.data.get("barcodes", [])  # expect list
        agent_id = request.data.get("agent_id")
        vehicle_id = request.data.get("vehicle_id")
        batchno = request.data.get("batchno")

        if not barcodes:
            return Response({"error": "No barcodes provided"}, status=400)

        # ===============================
        # ✅ FETCH AGENT
        # ===============================
        try:
            agent = User.objects.get(id=agent_id)
            agent.dispatcher_flag = "Unavailable"
            agent.save()
        except User.DoesNotExist:
            return Response({"error": "Invalid dispatcher"}, status=400)

        # ===============================
        # ✅ FETCH VEHICLE
        # ===============================
        vehicle = None
        if vehicle_id:
            try:
                vehicle = Vehicle.objects.get(id=vehicle_id)
                vehicle.vehicleStatus = "In Use"
                vehicle.save()
            except Vehicle.DoesNotExist:
                return Response({"error": "Invalid vehicle"}, status=400)

            # =============================
            # Update the batch from pending to completed
            # =============================
            bn = driverpickup.objects.get(batch_no=batchno)
            bn.action_done = "Dispatched"
            bn.flag = "Completed"
            bn.save()

        # ===============================
        # ✅ FETCH ITEMS (LOCKED)
        # ===============================
        items = OrderItem.objects.select_for_update().filter(barcode__in=barcodes)

        if items.count() != len(barcodes):
            return Response({"error": "Some items not found"}, status=400)

        # ===============================
        # ✅ GROUPING STRUCTURE
        # ===============================
        grouped_items = defaultdict(list)

        # ===============================
        # ✅ PROCESS ITEMS
        # ===============================
        for item in items:

            # 🚫 Must be in warehouse
            if item.flag not in ["WAREHOUSE", "IN_HUB_TRANSFER"]:
                raise Exception(f"Item {item.id} is not in warehouse")

            # 🚫 Prevent double dispatch
            if item.flag == "PICKED_UP":
                raise Exception(f"Item {item.id} already dispatched")

            # ===============================
            # ✅ UPDATE WAREHOUSE SCAN
            # ===============================
            scan = getattr(item, "warehouse_scan", None)
            if scan and not scan.time_out:
                scan.time_out = timezone.now()
                scan.updatedBy = request.user.fullName
                scan.flag = "PICKED_UP"
                scan.save()

            # ===============================
            # ✅ GROUP KEY (receiver + batch)
            # ===============================
            group_key = (item.receiver_email, batchno)
            grouped_items[group_key].append(item)

        # ===============================
        # ✅ PROCESS GROUPS (ONE OTP EACH)
        # ===============================
        for (receiver_email, batchno), items_group in grouped_items.items():

            otp = generate_delivery_code()

            for item in items_group:
                # CREATE DISPATCH
                Dispatch.objects.create(
                    order_item=item,
                    agent=agent,
                    vehicle=vehicle,
                    status="PICKED_UP",
                    picked_up_at=timezone.now(),
                    picked_up_by=agent,
                    assigned_by=request.user,
                    batch_no=batchno,
                )

                # UPDATE ITEM
                item.flag = "PICKED_UP"
                item.delivery_otp = otp
                item.waybillNo = generate_waybill_no(
                    item.state.code if item.state else "XXX"
                )
                item.save()

                create_tracking(
                    order_item=item,
                    stage="PICKED_UP",
                    user=request.user,
                    remark="Item Picked Up for Delivery",
                )

            # ===============================
            # ✅ SEND ONE EMAIL PER RECEIVER
            # ===============================
            first_item = items_group[0]

            context = {
                "receiver": first_item.receiver_name,
                "otp": otp,
                "items": items_group,
                "agent_name": agent.fullName,
                "agent_phone": agent.mobileNo,
                "vehicle_no": vehicle.vehicleNo if vehicle else "N/A",
                "vehicle_tag": vehicle.vehicleTag if vehicle else "N/A",
                "year": timezone.now().year,
            }

            subject = "Your Items Are Out for Delivery - OTP Inside"
            cc_email = first_item.sender_email

            html_content = render_to_string("emails/pickup_bulk.html", context)

            email = EmailMultiAlternatives(
                subject,
                "",
                settings.DEFAULT_FROM_EMAIL,
                to=[receiver_email],
                cc=[cc_email] if cc_email else [],
            )
            email.attach_alternative(html_content, "text/html")
            email.send()

        return Response({"message": "Bulk dispatch successful"}, status=201)

    @transaction.atomic
    def put(self, request):
        barcodes = request.data.get("barcodes", [])  # expect list
        agent_id = request.data.get("agent_id")
        vehicle_id = request.data.get("vehicle_id")
        batchno = request.data.get("batchno")

        if not barcodes:
            return Response({"error": "No barcodes provided"}, status=400)

        # ===============================
        # ✅ FETCH AGENT
        # ===============================
        try:
            agent = User.objects.get(id=agent_id)
            agent.dispatcher_flag = "Unavailable"
            agent.save()
        except User.DoesNotExist:
            return Response({"error": "Invalid dispatcher"}, status=400)

        # ===============================
        # ✅ FETCH VEHICLE
        # ===============================
        vehicle = None
        if vehicle_id:
            try:
                vehicle = Vehicle.objects.get(id=vehicle_id)
                vehicle.vehicleStatus = "In Use"
                vehicle.save()
            except Vehicle.DoesNotExist:
                return Response({"error": "Invalid vehicle"}, status=400)

            # =============================
            # Update the batch from pending to completed
            # =============================
            bn = driverpickup.objects.get(batch_no=batchno)
            bn.action_done = "Dispatched"
            bn.flag = "Completed"
            bn.save()

        # ===============================
        # ✅ FETCH ITEMS (LOCKED)
        # ===============================
        items = OrderItem.objects.select_for_update().filter(barcode__in=barcodes)

        # Transfer Item from hub
        transferitem = HubTransferItem.objects.select_for_update().filter(
            barcode__in=barcodes
        )
        transferitem.update(flag="PICKED_UP")

        if items.count() != len(barcodes):
            return Response({"error": "Some items not found"}, status=400)

        # ===============================
        # ✅ GROUPING STRUCTURE
        # ===============================
        grouped_items = defaultdict(list)

        # ===============================
        # ✅ PROCESS ITEMS
        # ===============================
        for item in items:

            # 🚫 Must be in warehouse
            if item.flag not in ["WAREHOUSE", "IN_HUB_TRANSFER"]:
                raise Exception(f"Item {item.id} is not in warehouse")

            # 🚫 Prevent double dispatch
            if item.flag == "PICKED_UP":
                raise Exception(f"Item {item.id} already dispatched")

            # ===============================
            # ✅ UPDATE WAREHOUSE SCAN
            # ===============================
            create_tracking(
                order_item=item,
                stage="HUB_TRANSFER",
                user=request.user,
                remark="Item Transferred to Hub",
            )
            scan = getattr(item, "warehouse_scan", None)
            # scan = WarehouseScan.objects.filter(item=item).first()
            if scan:  # and not scan.time_out:
                scan.time_out = timezone.now()
                scan.updatedBy = request.user.fullName
                scan.flag = "PICKED_UP"
                scan.save()

                # ===============================
                # ✅ UPDATE ORDER ITEM
                # ===============================

                item.flag = "PICKED_UP"
                scan.save()

            # ===============================
            # ✅ GROUP KEY (receiver + batch)
            # ===============================
            group_key = (item.receiver_email, batchno)
            grouped_items[group_key].append(item)

        # ===============================
        # ✅ PROCESS GROUPS (ONE OTP EACH)
        # ===============================
        for (receiver_email, batchno), items_group in grouped_items.items():

            otp = generate_delivery_code()

            for item in items_group:
                # CREATE DISPATCH
                HubScan.objects.create(
                    transfer_item=transferitem.get(barcode=item.barcode),
                    agent=agent,
                    vehicle=vehicle,
                    flag="PICKED_UP",
                    created_at=timezone.now(),
                    scanned_by=request.user,
                )
                create_tracking(
                    order_item=item,
                    stage="PICKED_UP_FROM_HUB",
                    user=self.context["request"].user,
                    remark="Item Picked up from Hub to Delivery",
                )
                # UPDATE ITEM
                item.flag = "PICKED_UP"
                item.delivery_otp = otp
                item.waybillNo = generate_waybill_no(
                    item.state.code if item.state else "XXX"
                )
                item.save()

            # ===============================
            # ✅ SEND ONE EMAIL PER RECEIVER
            # ===============================
            first_item = items_group[0]

            context = {
                "receiver": first_item.receiver_name,
                "otp": otp,
                "items": items_group,
                "agent_name": agent.fullName,
                "agent_phone": agent.mobileNo,
                "vehicle_no": vehicle.vehicleNo if vehicle else "N/A",
                "vehicle_tag": vehicle.vehicleTag if vehicle else "N/A",
                "year": timezone.now().year,
            }

            subject = "Your Items Are Out for Delivery - OTP Inside"
            cc_email = first_item.sender_email

            html_content = render_to_string("emails/pickup_bulk.html", context)

            email = EmailMultiAlternatives(
                subject,
                "",
                settings.DEFAULT_FROM_EMAIL,
                to=[receiver_email],
                cc=[cc_email] if cc_email else [],
            )
            email.attach_alternative(html_content, "text/html")
            email.send()

        return Response({"message": "Bulk dispatch successful"}, status=200)


class ValidateBarcodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        barcode = request.data.get("barcode")

        try:
            item = OrderItem.objects.get(barcode=barcode)
        except OrderItem.DoesNotExist:
            return Response({"error": "Invalid barcode"}, status=400)

        if item.flag != "WAREHOUSE":
            return Response({"error": "Item not in warehouse"}, status=400)

        if item.flag == "PICKUP":
            return Response({"error": "Already dispatched"}, status=400)

        return Response(
            {
                "valid": True,
                "item": {
                    "receiver_name": item.receiver_name,
                    "receiver_address": item.delivery_address,
                    "receiver_phone": item.receiver_phone,
                    "weight": item.weight,
                },
            }
        )


class ValidateHubBarcodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        barcode = request.data.get("barcode")

        if not barcode:
            return Response(
                {"error": "Barcode is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # -------------------------------------------------
        # Step 1: Validate barcode from HubTransferItem
        # -------------------------------------------------
        try:
            hub_item = HubTransferItem.objects.get(barcode=barcode)
        except HubTransferItem.DoesNotExist:
            return Response(
                {"error": "Invalid barcode"}, status=status.HTTP_400_BAD_REQUEST
            )

        # -------------------------------------------------
        # Step 2: Validate HubTransferItem status
        # -------------------------------------------------
        if hub_item.flag != "WAREHOUSE":
            return Response(
                {"error": "Item not yet received in warehouse"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hub_item.flag == "PICKUP":
            return Response(
                {"error": "Already dispatched"}, status=status.HTTP_400_BAD_REQUEST
            )

        # -------------------------------------------------
        # Step 3: Fetch full details from OrderItem
        # using the same barcode
        # -------------------------------------------------
        try:
            item = OrderItem.objects.get(barcode=barcode)
        except OrderItem.DoesNotExist:
            return Response(
                {"error": "Order item not found"}, status=status.HTTP_400_BAD_REQUEST
            )

        # -------------------------------------------------
        # Step 4: Return response
        # -------------------------------------------------
        return Response(
            {
                "valid": True,
                "item": {
                    "receiver_name": item.receiver_name,
                    "receiver_address": item.delivery_address,
                    "receiver_phone": item.receiver_phone,
                    "weight": item.weight,
                    "barcode": item.barcode,
                },
            },
            status=status.HTTP_200_OK,
        )


class PartnerCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vehicles = LogisticsPartner.objects.all().order_by("-created_at")
        serializer = PartnerSerializer(vehicles, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = PartnerSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(createdBy=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PartnerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(LogisticsPartner, pk=pk)

    def get(self, request, pk):
        partner = self.get_object(pk)
        serializer = PartnerSerializer(partner)  # ✅ use serializer
        return Response(serializer.data)

    def patch(self, request, pk):
        partner = self.get_object(pk)
        serializer = PartnerSerializer(
            partner, data=request.data, partial=True
        )  # ✅ use serializer

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        partner = self.get_object(pk)
        # You might want to check if partner has vehicles assigned instead of vehicleStatus
        partner.delete()
        return Response(
            {"message": "Deleted successfully"}, status=status.HTTP_204_NO_CONTENT
        )


class OrderByStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_param = request.query_params.get("status")
        # print("Status param:", status_param)  # Debugging line

        if not status_param:
            return Response({"error": "Status query parameter is required"}, status=400)

        items = (
            OrderItem.objects.filter(flag=status_param)
            .select_related("order")
            .order_by("-scanned_at")
        )
        # print(f"Found {items.count()} items with status {status_param}")  # Debugging line
        data = [
            {
                "barcode": item.barcode,
                "receiver": item.receiver_name,
                "address": item.delivery_address,
                "phone": item.receiver_phone,
                "order_id": str(item.order.id),
                "vendor": item.order.vendor.fullName if item.order.vendor else None,
                "weight": item.weight,
                "state": item.state.name if item.state else None,
                "lga": item.lga.name if item.lga else None,
                "zone": item.zone.name if item.zone else None,
                "time_in": item.scanned_at,
                "flag": item.flag,
            }
            for item in items
        ]

        return Response(data, status=200)


class DispatchedOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_param = request.query_params.get("status")
        # print("Status param:", status_param)  # Debugging line

        if not status_param:
            return Response({"error": "Status query parameter is required"}, status=400)

        # items = OrderItem.objects.filter(flag=status_param).select_related('order').order_by('-scanned_at')
        items = (
            OrderItem.objects.filter(flag=status_param)
            .select_related(
                "order",
                "order__vendor",
                "state",
                "lga",
                "zone",
                "dispatch__agent",
                "dispatch__vehicle",
            )
            .order_by("-scanned_at")
        )
        # print(f"Found {items.count()} items with status {status_param}")  # Debugging line
        data = [
            {
                "barcode": item.barcode,
                "receiver": item.receiver_name,
                "address": item.delivery_address,
                "phone": item.receiver_phone,
                # Order
                "order_id": str(item.order.id),
                "vendor": item.order.vendor.fullName if item.order.vendor else None,
                # Location
                "state": item.state.name if item.state else None,
                "lga": item.lga.name if item.lga else None,
                "zone": item.zone.name if item.zone else None,
                # Item
                "weight": item.weight,
                "time_in": item.scanned_at,
                "flag": item.flag,
                # Dispatch
                "agent": (
                    item.dispatch.agent.fullName if hasattr(item, "dispatch") else None
                ),
                "vehicle": (
                    item.dispatch.vehicle.vehicleNo
                    if item.dispatch and item.dispatch.vehicle
                    else None
                ),
                "dispatch_status": (
                    item.dispatch.status if hasattr(item, "dispatch") else None
                ),
                "assigned_at": (
                    item.dispatch.assigned_at if hasattr(item, "dispatch") else None
                ),
            }
            for item in items
        ]

        return Response(data, status=200)

    # @transaction.atomic
    # def patch(self, request):
    #     barcode = request.data.get("barcode")

    #     if not barcode:
    #         return Response({"error": "Barcode is required"}, status=400)

    #     try:
    #         item = OrderItem.objects.select_for_update().get(barcode=barcode)
    #     except OrderItem.DoesNotExist:
    #         return Response({"error": "Item not found"}, status=404)

    #     if not hasattr(item, "dispatch"):
    #         return Response({"error": "Dispatch record not found"}, status=400)

    #     dispatch = item.dispatch

    #     # ✅ 1. Prevent double pickup
    #     if dispatch.status == "PICKED_UP":
    #         #SEND email to the customer:
    #         # containing - OTP,Dispatcher Name, Phone No, Vehicle No

    #         return Response({"error": "Item already picked"}, status=400)

    #     # ✅ 2. Enforce correct workflow state
    #     if dispatch.status not in ["ASSIGNED", "OUT_FOR_DELIVERY"]:
    #         return Response(
    #             {"error": f"Invalid state transition from {dispatch.status}"},
    #             status=400
    #         )

    #     # ✅ 3. Ensure correct dispatcher (VERY IMPORTANT)
    #     if dispatch.agent != request.user:
    #         return Response(
    #             {"error": "This item is not assigned to you"},
    #             status=403
    #         )

    #     # ✅ UPDATE DISPATCH
    #     dispatch.status = "PICKED_UP"
    #     dispatch.picked_up_at = timezone.now()
    #     dispatch.picked_up_by = request.user
    #     dispatch.save()

    #     # ✅ UPDATE ORDER ITEM
    #     item.flag = "PICKED_UP"
    #     item.save()

    #     # ✅ UPDATE WAREHOUSE SCAN
    #     scan = getattr(item, "warehouse_scan", None)
    #     if scan:
    #         scan.flag = "PICKED_UP"
    #         scan.time_out = scan.time_out or timezone.now()
    #         scan.save()

    #     return Response({
    #         "message": "Item picked successfully",
    #         "barcode": barcode,
    #         "picked_by": request.user.id,
    #         "picked_at": dispatch.picked_up_at
    #     }, status=200)

    @transaction.atomic
    def patch(self, request):
        barcode = request.data.get("barcode")

        if not barcode:
            return Response({"error": "Barcode is required"}, status=400)

        try:
            item = OrderItem.objects.select_for_update().get(barcode=barcode)
        except OrderItem.DoesNotExist:
            return Response({"error": "Item not found"}, status=404)

        if not hasattr(item, "dispatch"):
            return Response({"error": "Dispatch record not found"}, status=400)

        dispatch = item.dispatch

        # ✅ Prevent double pickup
        if dispatch.status == "PICKED_UP":
            return Response({"error": "Item already picked"}, status=400)

        # ✅ Enforce workflow
        if dispatch.status not in ["ASSIGNED", "OUT_FOR_DELIVERY"]:
            return Response(
                {"error": f"Invalid state transition from {dispatch.status}"},
                status=400,
            )

        # ✅ Ensure correct dispatcher
        if dispatch.agent != request.user:
            return Response({"error": "This item is not assigned to you"}, status=403)

        # ===============================
        # ✅ GENERATE OTP
        # ===============================
        # otp = generate_otp()

        # OPTIONAL: save OTP to item or dispatch
        # dispatch.delivery_otp = otp
        # dispatch.otp_created_at = timezone.now()

        # ===============================
        # ✅ UPDATE DISPATCH
        # ===============================
        dispatch.status = "PICKED_UP"
        dispatch.picked_up_at = timezone.now()
        dispatch.picked_up_by = request.user
        dispatch.save()

        # ===============================
        # ✅ UPDATE ORDER ITEM
        # ===============================
        item.flag = "PICKED_UP"
        item.save()

        # ===============================
        # ✅ UPDATE WAREHOUSE SCAN
        # ===============================
        scan = getattr(item, "warehouse_scan", None)
        if scan:
            scan.flag = "PICKED_UP"
            scan.time_out = scan.time_out or timezone.now()
            scan.save()

        # ===============================
        # ✅ PREPARE EMAIL DATA
        # ===============================
        agent = dispatch.agent
        vehicle = dispatch.vehicle

        context = {
            "receiver": item.receiver_name,
            "otp": item.delivery_otp,
            "waybill": item.waybillNo,
            "item": item,
            "agent_name": agent.fullName,
            "agent_phone": agent.mobileNo,
            "vehicle_no": vehicle.vehicleNo if vehicle else "N/A",
            "vehicle_tag": vehicle.vehicleTag if vehicle else "N/A",
            "year": timezone.now().year,
        }

        # ===============================
        # ✅ SEND EMAIL
        # ===============================
        subject = "Your Item is Out for Delivery - OTP Inside"
        to_email = item.receiver_email  # make sure this field exists
        cc_email = item.sender_email

        html_content = render_to_string("emails/pickup.html", context)

        email = EmailMultiAlternatives(
            subject,
            "",
            settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
            cc=[cc_email] if cc_email else [],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        return Response(
            {
                "message": "Item picked successfully & email sent",
                "barcode": barcode,
                "otp": item.delivery_otp,
                "picked_by": request.user.id,
                "picked_at": dispatch.picked_up_at,
            },
            status=200,
        )


class MyDispatchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = Dispatch.objects.filter(
            status__in=["PICKUP", "IN_HUB_TRANSFER"]
        ).select_related("order_item", "vehicle")

        serializer = DispatchSerializer(items, many=True)

        return Response(serializer.data, status=200)


class AllMyDispatchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = Dispatch.objects.filter(agent=request.user).select_related(
            "order_item", "vehicle"
        )

        serializer = DispatchSerializer(items, many=True)
        # print(serializer.data) #debuggng

        return Response(serializer.data, status=200)


VALID_STATUSES = [
    "IN_TRANSIT",
    "DELIVERED",
    "ISSUE",
    "PART_DELIVERED",
    "RETURNED",
    "DAMAGED",
    "LOST",
]

ISSUE_REQUIRED_STATUSES = [
    "ISSUE",
    "RETURNED",
    "DAMAGED",
    "LOST",
    "PART_DELIVERED",
]


class UpdateDeliveryStatus(APIView):
    def patch(self, request):
        barcode = request.data.get("barcode")
        status = request.data.get("status")
        otp = request.data.get("otp")
        issue = request.data.get("issue")

        # ✅ Validate input
        if not barcode or not status:
            return Response(
                {"error": "Barcode and status are required"},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if status not in VALID_STATUSES:
            return Response(
                {"error": "Invalid status"},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = OrderItem.objects.get(barcode=barcode)
        except OrderItem.DoesNotExist:
            return Response(
                {"error": "Item not found"},
                status=http_status.HTTP_404_NOT_FOUND,
            )

        # ✅ OTP validation
        if status == "DELIVERED":
            if not otp:
                return Response(
                    {"error": "OTP is required for delivery"},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

            if item.delivery_otp != otp:
                return Response(
                    {"error": "Invalid OTP"},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

        # ✅ Issue validation
        if status in ISSUE_REQUIRED_STATUSES:
            if not issue or issue.strip() == "":
                return Response(
                    {"error": "Issue reason is required"},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )
        # update warehouse scan record if exists
        scan = getattr(item, "warehouse_scan", None)
        if scan:
            scan.flag = status
            scan.updatedBy = request.user.fullName
            scan.lastUpdatedat = timezone.now()
            scan.save()

        # ✅ Update OrderItem
        item.flag = status
        item.save()

        create_tracking(
            order_item=item,
            stage=status,
            user=request.user,
            remark="Item is " + status,
        )

        # ✅ Update Dispatch
        disp = getattr(item, "dispatch", None)
        if disp:
            disp.status = status
            create_tracking(
                order_item=item,
                stage=status,
                user=request.user,
                remark="Item is " + status,
            )
            # Save issue only when needed
            if status in ISSUE_REQUIRED_STATUSES:
                disp.issue_reason = issue

            # Only set delivered time when actually delivered
            if status == "DELIVERED":
                disp.delivered_at = timezone.now()

            disp.save()

        return Response({"message": "Status updated successfully"})


class UpdateDeliveryStatusFlag(APIView):

    @transaction.atomic
    def patch(self, request):

        barcodes = request.data.get("barcodes", [])
        status = request.data.get("status")
        otp = request.data.get("otp")
        issue = request.data.get("issue")

        # ✅ Validate input
        if not barcodes or not isinstance(barcodes, list):
            return Response(
                {"error": "Barcodes list is required"},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if not status:
            return Response(
                {"error": "Status is required"},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        if status not in VALID_STATUSES:
            return Response(
                {"error": "Invalid status"},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # ✅ Fetch all items
        items = OrderItem.objects.filter(barcode__in=barcodes)

        if not items.exists():
            return Response(
                {"error": "No items found"},
                status=http_status.HTTP_404_NOT_FOUND,
            )

        # ✅ OTP validation
        if status == "DELIVERED":

            if not otp:
                return Response(
                    {"error": "OTP is required for delivery"},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

            # Validate against first item
            first_item = items.first()

            if first_item.delivery_otp != otp:
                return Response(
                    {"error": "Invalid OTP"},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

        # ✅ Issue validation
        if status in ISSUE_REQUIRED_STATUSES:

            if not issue or issue.strip() == "":
                return Response(
                    {"error": "Issue reason is required"},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )

        updated_items = []

        # ✅ Loop through all grouped items
        for item in items:

            # -----------------------------------
            # UPDATE WAREHOUSE SCAN
            # -----------------------------------
            scan = getattr(item, "warehouse_scan", None)

            if scan:
                scan.flag = status
                scan.updatedBy = request.user.fullName
                scan.lastUpdatedat = timezone.now()
                scan.save()

            # -----------------------------------
            # UPDATE ORDER ITEM
            # -----------------------------------
            item.flag = status
            item.save()

            # -----------------------------------
            # TRACKING
            # -----------------------------------
            create_tracking(
                order_item=item,
                stage=status,
                user=request.user,
                remark=f"Item is {status}",
            )

            # -----------------------------------
            # UPDATE DISPATCH
            # -----------------------------------
            disp = getattr(item, "dispatch", None)

            if disp:

                disp.status = status

                # Save issue reason
                if status in ISSUE_REQUIRED_STATUSES:
                    disp.issue_reason = issue

                # Delivered timestamp
                if status == "DELIVERED":
                    disp.delivered_at = timezone.now()

                disp.save()

            updated_items.append(item.barcode)

        return Response(
            {
                "message": "Bulk status updated successfully",
                "updated": updated_items,
                "count": len(updated_items),
            }
        )


def reassign_dispatch(dispatch, new_agent, new_vehicle, user):
    DispatchHistory.objects.create(
        dispatch=dispatch,
        old_agent=dispatch.agent,
        new_agent=new_agent,
        old_vehicle=dispatch.vehicle,
        new_vehicle=new_vehicle,
        changed_by=user,
    )

    dispatch.agent = new_agent
    dispatch.vehicle = new_vehicle
    dispatch.reassigned_at = timezone.now()
    dispatch.save()


class UpdateAgentLocation(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        lat = request.data.get("latitude")
        lng = request.data.get("longitude")
        barcode = request.data.get("barcode")

        if not lat or not lng:
            return Response({"error": "Latitude and Longitude required"}, status=400)

        AgentLocation.objects.create(
            agent=request.user, latitude=lat, longitude=lng, barcode=barcode
        )

        return Response({"message": "Location updated"})


class AgentMovementTrail(APIView):
    def get(self, request):
        try:
            # Subquery to get the latest vehicle assigned to the agent
            latest_dispatch_subquery = (
                Dispatch.objects.filter(agent=OuterRef("agent_id"))
                .order_by("-assigned_at")
                .values("vehicle__vehicleNo")[:1]
            )

            # Fetch locations and annotate with vehicle
            qs = (
                AgentLocation.objects.select_related("agent")
                .annotate(vehicle_no=Subquery(latest_dispatch_subquery))
                .order_by("timestamp")
            )

            # Build response
            data = [
                {
                    "lat": loc.latitude,
                    "lng": loc.longitude,
                    "agent": loc.agent.fullName,
                    "barcode": loc.barcode,
                    "vehicle": loc.vehicle_no,  # Already annotated
                }
                for loc in qs
            ]

            return JsonResponse(data, safe=False)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class HubViewSet(AuditedModelViewSet):
    queryset = Hub.objects.all().order_by("-createdAt")
    serializer_class = HubSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Hub"


class HubTransferViewSet(AuditedModelViewSet):
    queryset = HubTransfer.objects.all().order_by("-created_at")
    serializer_class = HubTransferSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Hub Transfer"


class HubstoreViewSet(AuditedModelViewSet):
    serializer_class = HubStoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user_hub = self.request.user.hub_name

        order_items = OrderItem.objects.filter(barcode=OuterRef("barcode"))

        return (
            HubTransferItem.objects.filter(transfer__desthub=user_hub)
            .annotate(
                receiver_name=Subquery(order_items.values("receiver_name")[:1]),
                delivery_address=Subquery(order_items.values("delivery_address")[:1]),
                waybillNo=Subquery(order_items.values("waybillNo")[:1]),
                holding_period=Subquery(order_items.values("holding_period")[:1]),
                # flag=Subquery(order_items.values("flag")[:1]),
                batch_no=Subquery(
                    HubTransfer.objects.filter(id=OuterRef("transfer_id")).values(
                        "batch_no__batch_no"
                    )[:1]
                ),
            )
            .select_related("transfer", "transfer__desthub")
            .order_by("-id")
        )
