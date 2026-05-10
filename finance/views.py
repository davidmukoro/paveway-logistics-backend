from django.shortcuts import render
from rest_framework import viewsets, permissions
from .models import Expense, IouRequest, WalletFunding
from setup.models import User
from .serializers import ExpenseSerializer, IouRequestSerializer, WalletSerializer
from rest_framework import generics
from rest_framework.views import APIView
from django.db.models import Sum, Count, Q
from rest_framework.response import responses, Response
from setup.utils import AuditedModelViewSet


class WalletFundingViewSet(AuditedModelViewSet):
    queryset = WalletFunding.objects.all().order_by("-transactionDate")
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Wallet Funding"


class CustomerWalletBalance(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        user = User.objects.get(pk=id)
        if user.cPayType == "Postpaid":
            expense = (
                WalletFunding.objects.filter(customer_id=id).aggregate(
                    total=Sum("amount")
                )["total"]
                or 0.00
            )
            total_balance = float(user.creditLimit) + float(expense)
        else:
            total_balance = (
                WalletFunding.objects.filter(customer_id=id).aggregate(
                    total=Sum("amount")
                )["total"]
                or 0.00
            )
        return Response({"customer_id": id, "total_balance": total_balance})


class WalletTransactions(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        user = User.objects.get(pk=id)
        expense = WalletFunding.objects.filter(customer=user).order_by(
            "-transactionDate"
        )
        serializer = WalletSerializer(expense, many=True)

        return Response(serializer.data, status=200)


class IouRequestViewSet(AuditedModelViewSet):
    queryset = IouRequest.objects.all().order_by("-requestDate")
    serializer_class = IouRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "IOU Request"


class MyIouRequests(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        user = User.objects.get(pk=id)
        iou_requests = IouRequest.objects.filter(staff=user).order_by("-requestDate")
        serializer = IouRequestSerializer(iou_requests, many=True)
        return Response(serializer.data, status=200)


class ExpenseViewSet(AuditedModelViewSet):
    queryset = Expense.objects.all().order_by("-expenseDate")
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]
    model_label = "Expense"
