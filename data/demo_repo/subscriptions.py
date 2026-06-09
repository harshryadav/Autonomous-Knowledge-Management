"""Subscription upgrades, prorated through the payment router."""

import payment_router
import utils


def upgrade_plan(merchant_id, currency, prorated_amount, subscription_id):
    result = payment_router.route_payment(
        merchant_id, currency, prorated_amount,
        idempotency_key=utils.new_reference(f"upg-{subscription_id}"),
    )
    return {"subscription": subscription_id, "provider": result["provider"]}
