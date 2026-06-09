"""Checkout flow: validate the cart and charge the customer."""

import auth_session
import payment_router
import utils


def checkout(token, merchant_id, cart, currency="usd"):
    session = auth_session.validate_session(token)
    total = sum(item["price"] * item["qty"] for item in cart)
    if total <= 0:
        raise ValueError("Cart total must be positive")

    reference = utils.new_reference("chk")
    result = payment_router.route_payment(
        merchant_id, currency, total, idempotency_key=reference
    )
    return {
        "user": session["user_id"],
        "charged": utils.format_money(total, currency),
        "provider": result["provider"],
        "reference": result["reference"],
    }
