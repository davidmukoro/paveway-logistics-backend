from django.db import models
from setup.models import User, ExpenseCategory


# Create your models here.
class WalletFunding(models.Model):
    customer = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name="customer_wallet"
    )
    transactionDate = models.DateField(auto_now_add=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    txnRef = models.CharField(max_length=50, default="")
    narration = models.CharField(max_length=200, default="")
    postedBy = models.CharField(max_length=200, default="")
    postedAt = models.DateTimeField(auto_now_add=True)
    txntype = models.CharField(max_length=20, default="Income")

    def __str__(self):
        return self.txnRef

    class Meta:
        db_table = "wallet_funding"


class IouRequest(models.Model):
    iouref = models.CharField(max_length=50, default="")
    staff = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name="iou_customer"
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    reason = models.CharField(max_length=200, default="")
    status = models.CharField(max_length=20, default="Pending")
    requestDate = models.DateField(auto_now_add=True)
    approvedBy = models.CharField(max_length=200, default="")
    approvedAt = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"IOU Request by {self.staff.username} for {self.amount}"

    class Meta:
        db_table = "iou_request"


class Expense(models.Model):
    staff = models.ForeignKey(
        User, on_delete=models.DO_NOTHING, related_name="expense_staff"
    )
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00)
    description = models.CharField(max_length=200, default="")
    expenseDate = models.DateField(blank=True, null=True)
    postedBy = models.CharField(max_length=200, default="")
    postedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Expense by {self.staff.username} for {self.amount}"

    class Meta:
        db_table = "expenses"
