"""Invoice settlement: charge outstanding invoices via the router."""

import payment_router
import utils


def settle_invoice(merchant_id, invoice):
    amount = utils.cents_to_units(invoice["total_cents"])
    result = payment_router.route_payment(
        merchant_id, invoice["currency"], amount,
        idempotency_key=invoice["invoice_id"],
    )
    return {"invoice": invoice["invoice_id"], "provider": result["provider"]}
