from django.db import models
from setup.models import User
import uuid
import calendar


# Create your models here.
class PayrollPeriod(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    month = models.PositiveSmallIntegerField()  # 1–12
    year = models.PositiveSmallIntegerField()  # 2025
    is_closed = models.BooleanField(default=False)
    createdBy = models.CharField(max_length=255, null=True, blank=True)
    createdAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("month", "year")

    def __str__(self):
        return f"{self.month}/{self.year}"

    @property
    def payroll_period_name(self):
        return f"{calendar.month_name[self.month]} {self.year}"


class PayrollRun(models.Model):
    """
    Represents a payroll run for a given period.
    Each run summarizes payroll records for all employees.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    period = models.ForeignKey("PayrollPeriod", on_delete=models.CASCADE)
    run_date = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=20, default="Pending"
    )  # e.g. Pending, Completed
    total_gross = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    createdBy = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = "Payroll Run"
        verbose_name_plural = "Payroll Runs"
        ordering = ["-run_date"]

    def __str__(self):
        return f"{self.period} ({self.status})"


class AllowanceDeduction(models.Model):
    name = models.CharField(max_length=100)
    allowDed = models.CharField(
        max_length=30
    )  # "Allowance" for allowance, "Deduction" for deduction
    description = models.TextField(blank=True, null=True)
    createdBy = models.CharField(max_length=255, null=True, blank=True)
    createdAt = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class PayrollRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(User, on_delete=models.CASCADE)
    period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    generated_on = models.DateTimeField(auto_now_add=True)
    approved_by = models.CharField(max_length=100, blank=True, null=True)
    run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="records",
    )

    class Meta:
        unique_together = ("employee", "period")

    def __str__(self):
        return f"{self.employee} - {self.period}"


class EmployeeAllowance(models.Model):
    employee = models.ForeignKey(User, on_delete=models.CASCADE)
    allowance = models.ForeignKey(AllowanceDeduction, on_delete=models.CASCADE)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2
    )  # could be amount or %
    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, null=True, blank=True
    )
    createdBy = models.CharField(max_length=255, null=True, blank=True)
    createdAt = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.employee.username


class EmployeeDeduction(models.Model):
    employee = models.ForeignKey(User, on_delete=models.CASCADE)
    deduction = models.ForeignKey(AllowanceDeduction, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, null=True, blank=True
    )
    createdBy = models.CharField(max_length=255, null=True, blank=True)
    createdAt = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.employee.username
