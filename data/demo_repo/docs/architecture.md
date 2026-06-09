# Architecture Notes

## Shared helpers

The `utils` module provides money formatting (`format_money`) and
reference generation (`new_reference`). Keep it dependency-free so any
module can import it safely.

## Checkout

The `checkout` flow validates the session, totals the cart, and
charges the customer. It is intentionally thin: all provider logic
lives elsewhere.
