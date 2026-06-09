"""Recurring billing runs that charge via the payment router."""

import payment_router


def run_billing_cycle(merchant_id, subscriptions_due):
    results = []
    for sub in subscriptions_due:
        outcome = payment_router.route_payment(
            merchant_id, sub["currency"], sub["amount"],
            idempotency_key=f"bill-{sub['subscription_id']}",
        )
        results.append({"subscription": sub["subscription_id"], **outcome})
    return results
