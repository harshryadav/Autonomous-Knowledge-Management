"""Admin console: routing overrides and audit access."""

import auth_session
import payment_router


def set_routing_override(token, merchant_id, provider):
    auth_session.require_role(token, "admin", "superuser")
    payment_router.register_override(merchant_id, provider)
    return {"merchant": merchant_id, "forced_provider": provider}


def view_audit_trail(token, merchant_id=None):
    auth_session.require_role(token, "admin", "superuser")
    return payment_router.audit_trail(merchant_id)
