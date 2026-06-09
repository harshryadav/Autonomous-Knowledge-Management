"""Shared helpers: money formatting and identifiers."""

import uuid

CURRENCY_SYMBOLS = {"usd": "$", "eur": "\u20ac", "gbp": "\u00a3", "jpy": "\u00a5"}


def format_money(amount, currency):
    symbol = CURRENCY_SYMBOLS.get(currency.lower(), currency.upper() + " ")
    return f"{symbol}{amount:,.2f}"


def new_reference(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def cents_to_units(cents):
    return cents / 100.0
