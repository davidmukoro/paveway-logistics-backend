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
    DriverDocument,
    HubTransfer,
    Order,
    OrderItem,
    VehicleDocument,
    WarehouseScan,
    LogisticsPartner,
    driverpickup,
    Hub,
    AgentLocation,
    HubTransferItem,
    HubScan,
    OrderItemTracking,
    DispatchSession,
    DispatchStop,
)
from .serializers import (
    BulkDispatchSerializer,
    DriverDocumentSerializer,
    OrderItemSerializer,
    OrderSerializer,
    VehicleDocumentSerializer,
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
    calculate_speed_mps,
    create_tracking,
    distance_meters,
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
from django.utils import timezone
from datetime import timedelta
from rest_framework.decorators import action
from .serializers import (
    PendingWarehouseScanReportSerializer,
    WarehouseHoldingReportSerializer,
)
from rest_framework.parsers import MultiPartParser, FormParser
from .services.osrm_service import get_route
from .models import DispatchRoutePoint, AgentCurrentLocation, RouteDeviation
from .services.deviation_service import check_route_deviation
from .services.stop_service import update_stop_completion, update_stop_completion


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


# class TodayRunView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request):

#         now = timezone.now()

#         start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

#         end_of_day = start_of_day + timedelta(days=1)

#         items = (
#             Dispatch.objects.filter(
#                 agent=request.user,
#                 picked_up_at__gte=start_of_day,
#                 picked_up_at__lt=end_of_day,
#             )
#             .select_related("order_item", "vehicle")
#             .order_by("order_item__delivery_address")
#         )

#         serializer = DispatchSerializer(items, many=True)
#         return Response(serializer.data, status=200)


# class TodayRunView(APIView):
#     permission_classes = [IsAuthenticated]

#     ACTIVE_STATUSES = [
#         "PICKED_UP",
#         "IN_TRANSIT",
#         "OUT_FOR_DELIVERY",
#         "ISSUE",
#         "PART_DELIVERED",
#     ]

#     def get(self, request):

#         dispatches = (
#             Dispatch.objects.filter(
#                 agent=request.user,
#                 status__in=self.ACTIVE_STATUSES,
#             )
#             .select_related(
#                 "order_item",
#                 "vehicle",
#             )
#             .order_by(
#                 "order_item__delivery_address",
#                 "order_item__receiver_email",
#                 "picked_up_at",
#             )
#         )

#         serializer = DispatchSerializer(dispatches, many=True)
#         data = serializer.data

#         gps_points = list(
#             AgentLocation.objects.filter(session__agent=request.user).order_by(
#                 "-timestamp"
#             )[:6]
#         )

#         gps_points.reverse()

#         speed = calculate_speed_mps(gps_points)
#         enriched_items = []
#         stops = []
#         for d, item in zip(dispatches, data):

#             order_item = d.order_item

#             if gps_points:
#                 current_lat = gps_points[-1].latitude
#                 current_lng = gps_points[-1].longitude
#             else:
#                 current_lat = current_lng = None

#             if current_lat is None or not order_item.latitude or speed == 0:
#                 item["distance_km"] = None
#                 item["eta_minutes"] = None

#             else:
#                 distance = distance_meters(
#                     current_lat,
#                     current_lng,
#                     order_item.latitude,
#                     order_item.longitude,
#                 )

#                 item["distance_km"] = round(distance / 1000, 2)

#                 eta_seconds = distance / speed
#                 item["eta_minutes"] = max(1, round(eta_seconds / 60))

#             stops.append(item)

#             stops.sort(key=lambda x: x.get("distance_km") or 999999)
#             for i, item in enumerate(stops):
#                 item["is_next_stop"] = i == 0
#             enriched_items.append(item)

#         total = dispatches.count()
#         delivered = Dispatch.objects.filter(
#             agent=request.user, status="DELIVERED"
#         ).count()

#         pending = total - delivered

#         return Response(
#             {
#                 "items": enriched_items,
#                 "grouped": {
#                     "total": total,
#                     "delivered": delivered,
#                     "pending": pending,
#                 },
#             }
#         )

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class TodayRunView(APIView):
    permission_classes = [IsAuthenticated]

    ACTIVE_STATUSES = [
        "PICKED_UP",
        "IN_TRANSIT",
        "OUT_FOR_DELIVERY",
        "ISSUE",
        "PART_DELIVERED",
    ]

    def get(self, request):

        # =========================
        # 1. ROUTE DATA (ACTIVE ONLY)
        # =========================
        dispatches = (
            Dispatch.objects.filter(
                agent=request.user,
                status__in=self.ACTIVE_STATUSES,
            )
            .select_related("order_item", "vehicle")
            .order_by(
                "order_item__delivery_address",
                "order_item__receiver_email",
                "picked_up_at",
            )
        )

        serializer = DispatchSerializer(dispatches, many=True)
        data = serializer.data

        # =========================
        # 2. GPS DATA
        # =========================
        gps_points = list(
            AgentLocation.objects.filter(session__agent=request.user).order_by(
                "-timestamp"
            )[:6]
        )

        gps_points.reverse()

        speed = calculate_speed_mps(gps_points)

        if gps_points:
            current_lat = gps_points[-1].latitude
            current_lng = gps_points[-1].longitude
        else:
            current_lat = None
            current_lng = None

        # =========================
        # 3. ENRICH ITEMS
        # =========================
        stops = []

        for d, item in zip(dispatches, data):

            order_item = d.order_item

            # distance + ETA
            if current_lat is None or not order_item.latitude or speed == 0:
                item["distance_km"] = None
                item["eta_minutes"] = None
            else:
                distance = distance_meters(
                    current_lat,
                    current_lng,
                    order_item.latitude,
                    order_item.longitude,
                )

                item["distance_km"] = round(distance / 1000, 2)

                eta_seconds = distance / speed
                item["eta_minutes"] = max(1, round(eta_seconds / 60))

            stops.append(item)

        # =========================
        # 4. ROUTE OPTIMIZATION
        # =========================
        stops.sort(key=lambda x: x.get("distance_km") or 999999)

        for i, item in enumerate(stops):
            item["is_next_stop"] = i == 0

        enriched_items = stops

        # =========================
        # 5. STATS (CORRECT LOGIC)
        # =========================
        all_dispatches = Dispatch.objects.filter(agent=request.user)

        total = all_dispatches.count()

        delivered = all_dispatches.filter(status="DELIVERED").count()

        pending = all_dispatches.exclude(status="DELIVERED").count()

        # =========================
        # 6. RESPONSE
        # =========================
        return Response(
            {
                "items": enriched_items,
                "grouped": {
                    "total": total,
                    "delivered": delivered,
                    "pending": pending,
                },
            }
        )


class RouteReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):

        session = (
            DispatchSession.objects.filter(
                id=session_id,
            )
            .select_related("agent", "vehicle")
            .first()
        )

        if not session:
            return Response({"error": "Session not found"}, status=404)

        # 🔒 security check (non-staff users can only view own sessions)
        if not request.user.is_staff and session.agent != request.user:
            return Response({"error": "Unauthorized"}, status=403)

        locations = AgentLocation.objects.filter(session=session).order_by("timestamp")

        # optional: limit for performance (important for long sessions)
        locations = locations[:2000]

        route = [
            {
                "lat": loc.latitude,
                "lng": loc.longitude,
                "timestamp": loc.timestamp.isoformat(),
            }
            for loc in locations
        ]

        return Response(
            {
                "session_id": session.id,
                "agent": session.agent.fullName,
                "vehicle": session.vehicle.vehicleNo if session.vehicle else None,
                "route": route,
                "points": len(route),
            }
        )


class AllMyDispatchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = (
            Dispatch.objects.filter(agent=request.user)
            .select_related("order_item", "vehicle")
            .order_by("-picked_up_at")
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


from .models import AgentCurrentLocation
import math


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class UpdateDispatchStatus(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        dispatch_id = request.data.get("dispatch_id")
        status = request.data.get("status")

        allowed = [
            "PICKED_UP",
            "IN_TRANSIT",
            "OUT_FOR_DELIVERY",
            "DELIVERED",
            "ISSUE",
        ]

        if status not in allowed:
            return Response({"error": "Invalid status"}, status=400)

        dispatch = Dispatch.objects.filter(id=dispatch_id, agent=request.user).first()

        if not dispatch:
            return Response({"error": "Dispatch not found"}, status=404)

        dispatch.status = status

        # timestamps
        if status == "PICKED_UP":
            dispatch.picked_up_at = timezone.now()

        if status == "DELIVERED":
            dispatch.delivered_at = timezone.now()

        dispatch.save()

        return Response({"message": "Status updated"})


# class StartDispatchSession(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request):

#         # prevent duplicate active session
#         session = DispatchSession.objects.filter(
#             agent=request.user, status="ACTIVE"
#         ).first()

#         if session:
#             return Response(
#                 {"session_id": session.id, "message": "Session already active"}
#             )

#         # get latest vehicle assignment
#         dispatch = (
#             Dispatch.objects.filter(agent=request.user)
#             .select_related("vehicle")
#             .order_by("-assigned_at")
#             .first()
#         )

#         # create session
#         session = DispatchSession.objects.create(
#             agent=request.user,
#             vehicle=dispatch.vehicle if dispatch else None,
#             status="ACTIVE",
#         )

#         # 🚚 GET TODAY'S ASSIGNED PARCELS
#         parcels = Dispatch.objects.filter(
#             agent=request.user,
#             status__in=["PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY"],
#         ).select_related("order_item")

#         # 🔥 AUTO TRANSITION TO IN_TRANSIT
#         updated = parcels.update(status="IN_TRANSIT")


#         return Response(
#             {
#                 "session_id": session.id,
#                 "vehicle": (
#                     dispatch.vehicle.vehicleNo
#                     if dispatch and dispatch.vehicle
#                     else None
#                 ),
#                 "parcels_activated": updated,
#                 "message": "Dispatch started successfully",
#             }
#         )
class StartDispatchSession(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # prevent duplicate active session
        session = DispatchSession.objects.filter(
            agent=request.user, status="ACTIVE"
        ).first()

        if session:
            return Response(
                {"session_id": session.id, "message": "Session already active"}
            )

        # get latest vehicle assignment
        dispatch = (
            Dispatch.objects.filter(agent=request.user)
            .select_related("vehicle")
            .order_by("-assigned_at")
            .first()
        )

        # create session
        session = DispatchSession.objects.create(
            agent=request.user,
            vehicle=dispatch.vehicle if dispatch else None,
            status="ACTIVE",
        )

        # ==================================
        # CREATE DELIVERY STOPS
        # ==================================

        parcels = Dispatch.objects.filter(
            agent=request.user,
            status__in=[
                "PICKED_UP",
                "IN_TRANSIT",
                "OUT_FOR_DELIVERY",
                "PARTIAL",
                "ISSUE",
                "RETURNED",
            ],
        ).select_related("order_item")

        grouped_stops = defaultdict(list)

        for parcel in parcels:

            item = parcel.order_item

            key = (
                item.receiver_email,
                item.delivery_address,
            )

            grouped_stops[key].append(item)

        stops_created = 0

        for index, ((email, address), items) in enumerate(
            grouped_stops.items(), start=1
        ):

            first_item = items[0]

            if not first_item.latitude or not first_item.longitude:
                continue

            stop = DispatchStop.objects.create(
                session=session,
                customer_name=first_item.receiver_name,
                address=first_item.delivery_address,
                latitude=first_item.latitude,
                longitude=first_item.longitude,
                sequence=index,
            )

            dispatch_items = Dispatch.objects.filter(order_item__in=items)

            stop.dispatches.set(dispatch_items)
            stops_created += 1

        # ==================================
        # GET DRIVER CURRENT LOCATION
        # ==================================

        current_location = AgentCurrentLocation.objects.filter(
            agent=request.user
        ).first()

        if current_location is None:
            return Response(
                {"message": "Driver current location not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==================================
        # GENERATE PLANNED ROUTES
        # ==================================

        current_location = AgentCurrentLocation.objects.filter(
            agent=request.user
        ).first()

        if current_location:

            origin_lat = current_location.latitude
            origin_lng = current_location.longitude

            stops = session.stops.order_by("sequence")

            for stop in stops:

                route = get_route(
                    origin_lat,
                    origin_lng,
                    stop.latitude,
                    stop.longitude,
                )
                if not route:
                    continue

                route_points = []

                for index, point in enumerate(route, start=1):

                    route_points.append(
                        DispatchRoutePoint(
                            stop=stop,
                            sequence=index,
                            latitude=point["lat"],
                            longitude=point["lng"],
                        )
                    )

                DispatchRoutePoint.objects.bulk_create(route_points)

                # Next stop starts where the previous stop ended
                origin_lat = stop.latitude
                origin_lng = stop.longitude

        # ==================================
        # MOVE PARCELS TO IN_TRANSIT
        # ==================================

        # updated = parcels.update(status="IN_TRANSIT")
        updated = parcels.filter(
            status__in=[
                "PICKED_UP",
            ]
        ).update(status="IN_TRANSIT")
        return Response(
            {
                "session_id": session.id,
                "vehicle": (
                    dispatch.vehicle.vehicleNo
                    if dispatch and dispatch.vehicle
                    else None
                ),
                "parcels_activated": updated,
                "stops_created": stops_created,
                "message": "Dispatch started successfully",
            }
        )


class StopDispatchSession(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session = DispatchSession.objects.filter(
            agent=request.user, status="ACTIVE"
        ).first()

        if not session:
            return Response({"message": "No active session"}, status=400)

        session.status = "COMPLETED"
        session.ended_at = timezone.now()
        session.save()

        return Response({"message": "Session ended"})


class ActiveDispatchSession(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        session = (
            DispatchSession.objects.filter(
                agent=request.user, status="ACTIVE", ended_at__isnull=True
            )
            .select_related("vehicle")
            .order_by("-started_at")
            .first()
        )

        if not session:
            return Response({}, status=200)

        return Response(
            {
                "id": session.id,
                "status": session.status,
                "started_at": session.started_at,
                "vehicle": (
                    {
                        "id": session.vehicle.id if session.vehicle else None,
                        "vehicleNo": (
                            session.vehicle.vehicleNo if session.vehicle else None
                        ),
                    }
                    if session.vehicle
                    else None
                ),
            }
        )


class UpdateAgentLocation(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")
        accuracy = request.data.get("accuracy")

        if latitude is None or longitude is None:
            return Response(
                {"error": "Latitude and Longitude required"},
                status=400,
            )

        current_lat = float(latitude)
        current_lng = float(longitude)

        # -------------------------------------------------------
        # Get Active Session
        # -------------------------------------------------------
        session = (
            DispatchSession.objects.filter(
                agent=request.user,
                status="ACTIVE",
            )
            .order_by("-started_at")
            .first()
        )

        if not session:
            return Response(
                {"error": "No active dispatch session"},
                status=400,
            )

        # -------------------------------------------------------
        # Save session starting point (only once)
        # -------------------------------------------------------
        if session.start_latitude is None or session.start_longitude is None:
            session.start_latitude = current_lat
            session.start_longitude = current_lng
            session.save(
                update_fields=[
                    "start_latitude",
                    "start_longitude",
                ]
            )

        # -------------------------------------------------------
        # Update current location
        # -------------------------------------------------------
        AgentCurrentLocation.objects.update_or_create(
            agent=request.user,
            defaults={
                "latitude": current_lat,
                "longitude": current_lng,
                "accuracy": accuracy,
            },
        )

        # -------------------------------------------------------
        # Save movement history
        # -------------------------------------------------------
        AgentLocation.objects.create(
            session=session,
            latitude=current_lat,
            longitude=current_lng,
            accuracy=accuracy,
        )
        # -------------------------------------------------------
        # Route Deviation Detection
        # -------------------------------------------------------

        deviation = check_route_deviation(
            session=session,
            latitude=current_lat,
            longitude=current_lng,
        )

        # -------------------------------------------------------
        # Calculate distance travelled from session start
        # (same value for every dispatch)
        # -------------------------------------------------------
        distance_from_start = distance_meters(
            session.start_latitude,
            session.start_longitude,
            current_lat,
            current_lng,
        )

        # -------------------------------------------------------
        # Update dispatch statuses automatically
        # -------------------------------------------------------
        dispatches = Dispatch.objects.filter(
            agent=request.user,
            status__in=[
                "PICKED_UP",
                "IN_TRANSIT",
            ],
        ).select_related("order_item")

        updated = 0

        for dispatch in dispatches:

            item = dispatch.order_item

            if item.latitude is None or item.longitude is None:
                continue

            # Distance between dispatcher and customer
            distance_to_customer = distance_meters(
                current_lat,
                current_lng,
                item.latitude,
                item.longitude,
            )

            # -----------------------------------------
            # Left warehouse
            # -----------------------------------------
            if dispatch.status == "PICKED_UP" and distance_from_start >= 500:
                dispatch.status = "IN_TRANSIT"
                dispatch.save(update_fields=["status"])
                updated += 1

            # -----------------------------------------
            # Arrived near customer
            # -----------------------------------------
            elif dispatch.status == "IN_TRANSIT" and distance_to_customer <= 300:
                dispatch.status = "OUT_FOR_DELIVERY"
                dispatch.save(update_fields=["status"])
                updated += 1

        return Response(
            {
                "message": "Location updated",
                "dispatches_updated": updated,
                "deviation_detected": (True if deviation else False),
                "deviation_distance": (
                    round(deviation.deviation_distance, 2) if deviation else None
                ),
            }
        )


class RouteDeviationHistory(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        deviations = RouteDeviation.objects.select_related(
            "session",
            "agent",
        ).order_by("-detected_at")

        data = []

        for deviation in deviations:

            data.append(
                {
                    "id": deviation.id,
                    "session_id": (deviation.session.id if deviation.session else None),
                    "agent": (deviation.agent.fullName if deviation.agent else None),
                    "latitude": deviation.latitude,
                    "longitude": deviation.longitude,
                    "planned_latitude": (deviation.planned_latitude),
                    "planned_longitude": (deviation.planned_longitude),
                    "distance": (
                        round(deviation.deviation_distance, 2)
                        if deviation.deviation_distance
                        else 0
                    ),
                    "status": deviation.status,
                    "detected_at": (deviation.detected_at),
                }
            )

        return Response(data)


class LiveDispatchers(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        sessions = (
            DispatchSession.objects.filter(status="ACTIVE")
            .select_related("agent", "vehicle")
            .prefetch_related("locations")
        )

        data = []

        for session in sessions:

            latest_location = session.locations.order_by("-timestamp").first()

            if not latest_location:
                continue

            # route history (last 50 points for performance)
            route = list(
                session.locations.order_by("-timestamp")[:50].values(
                    "latitude", "longitude", "timestamp"
                )
            )
            # =================================
            # PLANNED ROUTE
            # =================================

            planned_route = list(
                DispatchRoutePoint.objects.filter(stop__session=session)
                .order_by("stop__sequence", "sequence")
                .values("latitude", "longitude")
            )

            # =================================
            # ROUTE DEVIATIONS
            # =================================

            deviations = list(
                RouteDeviation.objects.filter(session=session)
                .order_by("-detected_at")
                .values(
                    "latitude",
                    "longitude",
                    "deviation_distance",
                    "detected_at",
                    "status",
                )
            )

            # idle time (simple version)
            idle_minutes = 0
            if latest_location:
                idle_minutes = int(
                    (timezone.now() - latest_location.timestamp).total_seconds() / 60
                )

            data.append(
                {
                    "session_id": session.id,
                    "agent": session.agent.fullName,
                    "agent_id": session.agent.id,
                    "vehicle": session.vehicle.vehicleNo if session.vehicle else None,
                    "latitude": latest_location.latitude,
                    "longitude": latest_location.longitude,
                    "accuracy": latest_location.accuracy,
                    "status": session.status,
                    "started_at": session.started_at,
                    "updated_at": latest_location.timestamp,
                    "idle_minutes": idle_minutes,
                    # route for replay
                    # ACTUAL GPS HISTORY
                    "route": [
                        {
                            "lat": p["latitude"],
                            "lng": p["longitude"],
                            "timestamp": p["timestamp"],
                        }
                        for p in route
                    ],
                    # PLANNED OSRM ROUTE
                    "planned_route": [
                        {
                            "lat": p["latitude"],
                            "lng": p["longitude"],
                        }
                        for p in planned_route
                    ],
                    "deviations": [
                        {
                            "lat": d["latitude"],
                            "lng": d["longitude"],
                            "distance": d["deviation_distance"],
                            "detected_at": d["detected_at"],
                            "status": d["status"],
                        }
                        for d in deviations
                    ],
                }
            )

        return Response(data)


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


class WarehouseScanViewSet(AuditedModelViewSet):
    queryset = WarehouseScan.objects.all()
    serializer_class = WarehouseHoldingReportSerializer

    @action(
        detail=False,
        methods=["get"],
        url_path="holding-period-report",
    )
    def holding_period_report(self, request):
        now = timezone.now()

        scans = (
            WarehouseScan.objects.select_related(
                "item",
                "item__state",
                "item__lga",
            )
            .filter(
                flag="IN_WAREHOUSE",
                time_out__isnull=True,
                item__flag="WAREHOUSE",
            )
            .order_by("-time_in")
        )

        exceeded_items = []

        for scan in scans:
            limit_time = scan.time_in + timedelta(hours=scan.item.holding_period)

            if now > limit_time:
                exceeded_items.append(scan)

        serializer = WarehouseHoldingReportSerializer(
            exceeded_items,
            many=True,
        )

        total_items = len(exceeded_items)
        total_worth = sum([item.item.worth for item in exceeded_items])

        return Response(
            {
                "count": total_items,
                "totalWorth": total_worth,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import OrderItem
from .serializers import PendingWarehouseScanReportSerializer


class PendingWarehouseScanReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        queryset = (
            OrderItem.objects.filter(
                flag="PENDING",
                scanned_at__isnull=False,
            )
            .select_related(
                "order",
                "order__vendor",
                "state",
                "lga",
                "zone",
            )
            .order_by("scanned_at")
        )

        serializer = PendingWarehouseScanReportSerializer(
            queryset,
            many=True,
        )

        return Response(
            {
                "success": True,
                "count": queryset.count(),
                "data": serializer.data,
            }
        )


class VehicleDocumentViewSet(AuditedModelViewSet):

    queryset = VehicleDocument.objects.select_related("vehicle").all()
    permission_classes = [IsAuthenticated]
    serializer_class = VehicleDocumentSerializer

    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        serializer.save(createdBy=self.request.user.fullName)


class DriverDocumentViewSet(AuditedModelViewSet):

    queryset = DriverDocument.objects.select_related("driver").all()
    permission_classes = [IsAuthenticated]
    serializer_class = DriverDocumentSerializer

    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        serializer.save(createdBy=self.request.user.fullName)


from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import DispatchRoutePoint, DispatchSession
from .serializers import DispatchRoutePointSerializer


class CreateDispatchRoute(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        session_id = request.data.get("session_id")
        points = request.data.get("route")

        if not session_id:
            return Response(
                {"detail": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not points:
            return Response(
                {"detail": "route points are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = DispatchSession.objects.get(id=session_id)

        except DispatchSession.DoesNotExist:

            return Response(
                {"detail": "Dispatch session not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # remove existing planned route
        DispatchRoutePoint.objects.filter(session=session).delete()

        route_objects = []

        for index, point in enumerate(points):

            route_objects.append(
                DispatchRoutePoint(
                    session=session,
                    sequence=index + 1,
                    latitude=point["lat"],
                    longitude=point["lng"],
                )
            )

        DispatchRoutePoint.objects.bulk_create(route_objects)

        return Response(
            {"message": "Route saved successfully", "points_saved": len(route_objects)},
            status=status.HTTP_201_CREATED,
        )


from django.db.models import Count, Avg, Q


class RouteComplianceSummary(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        data = []

        agents = RouteDeviation.objects.values(
            "agent_id",
            "agent__fullName",
        ).annotate(
            total_deviations=Count("id"),
            open_deviations=Count("id", filter=Q(status="OPEN")),
            resolved_deviations=Count("id", filter=Q(status="RESOLVED")),
            average_distance=Avg("deviation_distance"),
        )

        for agent in agents:

            total = agent["total_deviations"]

            resolved = agent["resolved_deviations"]

            compliance = 100

            if total > 0:
                compliance = (resolved / total) * 100

            data.append(
                {
                    "agent_id": agent["agent_id"],
                    "agent": agent["agent__fullName"],
                    "total_deviations": total,
                    "open_deviations": agent["open_deviations"],
                    "resolved_deviations": resolved,
                    "average_distance": round(
                        agent["average_distance"] or 0,
                        2,
                    ),
                    "compliance_percentage": round(
                        compliance,
                        2,
                    ),
                }
            )

        return Response(data)


class TodayRunStopsView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        session = (
            DispatchSession.objects.filter(
                agent=request.user,
                status="ACTIVE",
            )
            .order_by("-started_at")
            .first()
        )

        if not session:
            return Response(
                {"error": "No active dispatch session"},
                status=400,
            )

        stops = session.stops.order_by("sequence")

        data = []

        # for stop in stops:

        #     dispatches = Dispatch.objects.filter(
        #         order_item__delivery_address=stop.address,
        #         agent=request.user,
        #         status__in=[
        #             "PICKED_UP",
        #             "IN_TRANSIT",
        #             "OUT_FOR_DELIVERY",
        #             "DELIVERED",
        #         ],
        #     )

        #     total_items = dispatches.count()

        #     delivered_items = dispatches.filter(status="DELIVERED").count()

        #     returned_items = dispatches.filter(status="RETURNED").count()

        #     issue_items = dispatches.filter(status="ISSUE").count()

        #     partial_items = dispatches.filter(status="PARTIAL").count()

        #     pending_items = dispatches.filter(
        #         status__in=[
        #             "ASSIGNED",
        #             "PICKED_UP",
        #             "IN_TRANSIT",
        #         ]
        #     ).count()
        for stop in session.stops.all():

            dispatches = stop.dispatches.all()

            total_items = dispatches.count()

            delivered_items = dispatches.filter(status="DELIVERED").count()

            returned_items = dispatches.filter(status="RETURNED").count()

            issue_items = dispatches.filter(status="ISSUE").count()
            partial_items = dispatches.filter(status="PARTIAL").count()

            final_statuses = [
                "DELIVERED",
                "RETURNED",
                "ISSUE",
                "DAMAGED",
                "LOST",
            ]

            pending_items = dispatches.exclude(status__in=final_statuses).count()

            completed = pending_items == 0
            if total_items > 0:
                progress_percent = round(
                    ((total_items - pending_items) / total_items) * 100
                )
            else:
                progress_percent = 0

            processed_items = total_items - pending_items

            if completed:
                stop_status = "COMPLETED"
            elif processed_items > 0:
                stop_status = "IN_PROGRESS"
            else:
                stop_status = "PENDING"

            data.append(
                {
                    "stop_id": stop.id,
                    "sequence": stop.sequence,
                    "customer_name": stop.customer_name,
                    "address": stop.address,
                    "latitude": stop.latitude,
                    "longitude": stop.longitude,
                    "total_items": total_items,
                    "pending_items": pending_items,
                    "delivered_items": delivered_items,
                    "returned_items": returned_items,
                    "issue_items": issue_items,
                    "partial_items": partial_items,
                    "completed": pending_items == 0,
                    "processed_items": processed_items,
                    "progress_percent": progress_percent,
                    "stop_status": stop_status,
                }
            )

        return Response(
            {
                "session_id": session.id,
                "stops": data,
            }
        )


class CompleteDeliveryView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):

        dispatch_id = request.data.get("dispatch_id")
        delivery_otp = request.data.get("delivery_otp")

        if not dispatch_id:
            return Response(
                {"error": "Dispatch ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not delivery_otp:
            return Response(
                {"error": "Delivery OTP is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================
        # GET DISPATCH
        # =====================================

        try:
            dispatch = (
                Dispatch.objects.select_for_update()
                .select_related("order_item")
                .get(
                    id=dispatch_id,
                    agent=request.user,
                )
            )

        except Dispatch.DoesNotExist:
            return Response(
                {"error": "Dispatch not found or not assigned to you"},
                status=status.HTTP_404_NOT_FOUND,
            )

        item = dispatch.order_item

        # =====================================
        # STATUS VALIDATION
        # =====================================

        if dispatch.status not in [
            "OUT_FOR_DELIVERY",
            "IN_TRANSIT",
        ]:
            return Response(
                {"error": f"Parcel cannot be delivered from status {dispatch.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================
        # OTP VALIDATION
        # =====================================

        if item.delivery_otp != delivery_otp:
            return Response(
                {"error": "Invalid delivery OTP"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================
        # COMPLETE DELIVERY
        # =====================================

        dispatch.status = "DELIVERED"
        dispatch.delivered_at = timezone.now()

        dispatch.save(
            update_fields=[
                "status",
                "delivered_at",
            ]
        )

        # Update item

        item.flag = "DELIVERED"
        item.save(
            update_fields=[
                "flag",
            ]
        )

        # =====================================
        # TRACKING HISTORY
        # =====================================

        create_tracking(
            order_item=item,
            stage="DELIVERED",
            user=request.user,
            remark="Item delivered successfully",
        )

        return Response(
            {
                "message": "Delivery completed successfully",
                "dispatch_id": dispatch.id,
                "barcode": item.barcode,
                "delivered_at": dispatch.delivered_at,
            },
            status=status.HTTP_200_OK,
        )


# class DispatchStopItemsView(APIView):

#     permission_classes = [IsAuthenticated]

#     def get(self, request, stop_id):

#         try:
#             stop = DispatchStop.objects.get(
#                 id=stop_id,
#                 session__agent=request.user,
#             )

#         except DispatchStop.DoesNotExist:

#             return Response(
#                 {"error": "Stop not found"},
#                 status=404,
#             )

#         dispatches = Dispatch.objects.filter(
#             agent=request.user,
#             order_item__delivery_address=stop.address,
#             status__in=[
#                 "PICKED_UP",
#                 "IN_TRANSIT",
#                 "OUT_FOR_DELIVERY",
#             ],
#         ).select_related("order_item")

#         items = []

#         for dispatch in dispatches:

#             items.append(
#                 {
#                     "dispatch_id": dispatch.id,
#                     "barcode": dispatch.order_item.barcode,
#                     "item_id": dispatch.order_item.id,
#                     "flag": dispatch.status,
#                     "remark": dispatch.issue_reason,
#                     "description": dispatch.order_item.description,
#                     "receiver_name": dispatch.order_item.receiver_name,
#                     "status": dispatch.status,
#                 }
#             )

#         return Response(
#             {
#                 "stop_id": stop.id,
#                 "customer": stop.customer_name,
#                 "items": items,
#             }
#         )


class DispatchStopItemsView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, stop_id):

        try:
            stop = DispatchStop.objects.get(
                id=stop_id,
                session__agent=request.user,
            )

        except DispatchStop.DoesNotExist:

            return Response(
                {"error": "Stop not found"},
                status=404,
            )

        # ====================================
        # GET ITEMS BELONGING TO THIS STOP ONLY
        # ====================================

        dispatches = stop.dispatches.select_related("order_item").all()

        items = []

        for dispatch in dispatches:

            item = dispatch.order_item
            editable = dispatch.status not in [
                "DELIVERED",
                "RETURNED",
                "ISSUE",
                "DAMAGED",
                "LOST",
            ]

            items.append(
                {
                    "dispatch_id": dispatch.id,
                    "item_id": str(item.id),
                    "barcode": item.barcode,
                    "flag": dispatch.status,
                    "status": dispatch.status,
                    "remark": dispatch.issue_reason,
                    "description": item.description,
                    "receiver_name": item.receiver_name,
                    "editable": editable,
                }
            )

        return Response(
            {
                "stop_id": stop.id,
                "customer": stop.customer_name,
                "completed": stop.completed,
                "items": items,
            }
        )


class UpdateDeliveryExceptionView(APIView):

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):

        dispatch_id = request.data.get("dispatch_id")
        exception_status = request.data.get("status")
        comment = request.data.get("comment")

        if not dispatch_id:
            return Response(
                {"error": "Dispatch ID is required"},
                status=400,
            )

        if exception_status not in [
            "PARTIAL",
            "RETURNED",
            "ISSUE",
        ]:
            return Response(
                {"error": "Invalid delivery exception status"},
                status=400,
            )

        if not comment:
            return Response(
                {"error": "Comment is required for exception status"},
                status=400,
            )

        try:

            dispatch = (
                Dispatch.objects.select_for_update()
                .select_related("order_item")
                .get(
                    id=dispatch_id,
                    agent=request.user,
                )
            )

        except Dispatch.DoesNotExist:

            return Response(
                {"error": "Dispatch not found"},
                status=404,
            )

        # ---------------------------------
        # Validate current state
        # ---------------------------------

        if dispatch.status == "DELIVERED":

            return Response(
                {"error": "Delivered parcel cannot be changed"},
                status=400,
            )

        # ---------------------------------
        # Update dispatch
        # ---------------------------------

        dispatch.status = exception_status

        dispatch.issue_reason = comment

        dispatch.save(
            update_fields=[
                "status",
                "issue_reason",
            ]
        )

        item = dispatch.order_item

        # ---------------------------------
        # Update item flag
        # ---------------------------------

        if exception_status == "RETURNED":

            item.flag = "INWARD_RETURNED"

        elif exception_status in [
            "PARTIAL",
            "ISSUE",
        ]:

            item.flag = "OUTWARD_RETURNED"

        item.save(update_fields=["flag"])

        # ---------------------------------
        # Tracking
        # ---------------------------------

        create_tracking(
            order_item=item,
            stage=exception_status,
            user=request.user,
            remark=comment,
        )

        return Response(
            {
                "message": "Delivery exception recorded",
                "dispatch_id": dispatch.id,
                "status": dispatch.status,
                "comment": dispatch.issue_reason,
            }
        )


class UpdateDeliveryStatusView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, item_id):

        status_value = request.data.get("status")
        comment = request.data.get("comment")
        otp = request.data.get("otp")

        allowed_status = [
            "DELIVERED",
            "PARTIAL",
            "RETURNED",
            "ISSUE",
        ]

        if status_value not in allowed_status:
            return Response({"error": "Invalid delivery status"}, status=400)

        item = get_object_or_404(OrderItem, id=item_id)

        dispatch = get_object_or_404(Dispatch, order_item=item, agent=request.user)

        # ==========================
        # COMMENT VALIDATION
        # ==========================

        if status_value in ["PARTIAL", "RETURNED", "ISSUE"]:

            if not comment:
                return Response(
                    {"error": "Comment is required for this status"}, status=400
                )

        # ==========================
        # OTP VALIDATION
        # ==========================

        if status_value == "DELIVERED":

            if not otp:
                return Response({"error": "Delivery OTP required"}, status=400)

            if otp != item.delivery_otp:

                return Response({"error": "Invalid delivery OTP"}, status=400)

        # ==========================
        # UPDATE DISPATCH
        # ==========================

        dispatch.status = status_value

        if status_value == "DELIVERED":

            dispatch.delivered_at = timezone.now()

        if status_value in ["PARTIAL", "RETURNED", "ISSUE"]:

            dispatch.issue_reason = comment

        dispatch.save()

        # ==========================
        # UPDATE ITEM STATUS
        # ==========================

        item.flag = status_value

        item.save(update_fields=["flag"])

        # ==========================
        # CREATE ITEM TRACKING
        # ==========================

        create_tracking(
            order_item=item, stage=status_value, user=request.user, remark=comment
        )

        # ==========================
        # UPDATE STOP COMPLETION
        # ==========================

        # for stop in dispatch.stops.all():
        # update_stop_completion(stop)

        # ==========================
        # CHECK STOP COMPLETION
        # ==========================

        # completed_stops = []

        # for stop in dispatch.stops.all():

        # completed = update_stop_completion(stop)

        # if completed:
        # completed_stops.append(stop.id)
        # ==========================
        # UPDATE STOP COMPLETION
        # ==========================

        completed_stops = []

        for stop in dispatch.stops.all():

            completed = update_stop_completion(stop)

            if completed:
                completed_stops.append(stop.id)

        return Response(
            {
                "message": f"Item updated to {status_value}",
                "status": status_value,
                "completed_stops": completed_stops,
            }
        )
