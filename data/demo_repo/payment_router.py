"""Route payment requests to the right provider."""

PROVIDERS = {
    "stripe": {"currencies": {"usd", "eur", "gbp"}, "max_amount": 999_999},
    "adyen": {"currencies": {"usd", "eur", "jpy", "gbp"}, "max_amount": 5_000_000},
    "local_bank": {"currencies": {"usd"}, "max_amount": 50_000},
}

RETRYABLE_ERRORS = {"timeout", "rate_limited", "provider_unavailable"}
MAX_RETRIES = 3

_routing_overrides = {}
_audit_log = []


class PaymentError(Exception):
    """Raised when a payment cannot be routed or processed."""


class ProviderUnavailable(PaymentError):
    """Raised when no provider can take the transaction."""


def register_override(merchant_id, provider):
    if provider not in PROVIDERS:
        raise PaymentError(f"Unknown provider: {provider}")
    _routing_overrides[merchant_id] = provider


def clear_override(merchant_id):
    _routing_overrides.pop(merchant_id, None)


def select_provider(merchant_id, currency, amount):
    override = _routing_overrides.get(merchant_id)
    if override:
        caps = PROVIDERS[override]
        if currency in caps["currencies"] and amount <= caps["max_amount"]:
            return override

    candidates = []
    for name, caps in PROVIDERS.items():
        if currency not in caps["currencies"]:
            continue
        if amount > caps["max_amount"]:
            continue
        candidates.append(name)

    if not candidates:
        raise ProviderUnavailable(
            f"No provider supports {amount} {currency.upper()}"
        )
    # Prefer the provider with the most headroom for this amount.
    candidates.sort(key=lambda n: PROVIDERS[n]["max_amount"], reverse=True)
    return candidates[0]


def route_payment(merchant_id, currency, amount, idempotency_key=None):
    if amount <= 0:
        raise PaymentError("Amount must be positive")
    currency = currency.lower()

    provider = select_provider(merchant_id, currency, amount)
    attempt = 0
    last_error = None

    while attempt < MAX_RETRIES:
        attempt += 1
        result = _dispatch(provider, merchant_id, currency, amount, idempotency_key)
        if result["status"] == "ok":
            _audit_log.append(
                {
                    "merchant": merchant_id,
                    "provider": provider,
                    "amount": amount,
                    "currency": currency,
                    "attempts": attempt,
                }
            )
            return result
        last_error = result["error"]
        if last_error not in RETRYABLE_ERRORS:
            break

    raise PaymentError(f"Payment failed after {attempt} attempt(s): {last_error}")


def route_refund(merchant_id, currency, amount, original_reference):
    if not original_reference:
        raise PaymentError("Refunds require the original payment reference")
    provider = select_provider(merchant_id, currency.lower(), amount)
    result = _dispatch(provider, merchant_id, currency, -amount, original_reference)
    if result["status"] != "ok":
        raise PaymentError(f"Refund failed: {result['error']}")
    return result


def audit_trail(merchant_id=None):
    if merchant_id is None:
        return list(_audit_log)
    return [entry for entry in _audit_log if entry["merchant"] == merchant_id]


def _dispatch(provider, merchant_id, currency, amount, reference):
    # Stand-in for the real provider SDK calls. Deterministic so the
    # demo behaves the same on every run.
    if provider == "local_bank" and abs(amount) > 25_000:
        return {"status": "error", "error": "rate_limited"}
    return {
        "status": "ok",
        "provider": provider,
        "reference": reference or f"{merchant_id}-{currency}-{abs(amount)}",
    }
