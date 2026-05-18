from django.db.models import Sum
from setup.models import User
from finance.models import WalletFunding


def compute_customer_wallet_balance(customer_id):
    user = User.objects.get(pk=customer_id)

    expense = (
        WalletFunding.objects.filter(customer_id=customer_id).aggregate(
            total=Sum("amount")
        )["total"]
        or 0.00
    )

    if user.cPayType == "Postpaid":
        total_balance = float(user.creditLimit) + float(expense)
    else:
        total_balance = float(expense)

    return total_balance
