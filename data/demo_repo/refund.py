"""Refund flow built on the payment router."""

import payment_router
import utils


def refund_order(merchant_id, currency, amount, original_reference):
    result = payment_router.route_refund(
        merchant_id, currency, amount, original_reference
    )
    return {
        "refunded": utils.format_money(amount, currency),
        "provider": result["provider"],
        "reference": result["reference"],
    }
