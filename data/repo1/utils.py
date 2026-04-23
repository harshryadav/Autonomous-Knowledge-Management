"""Miscellaneous helper functions."""


def add(a, b):
    """Return the sum of two numbers."""
    return a + b


def is_even(n):
    """True if `n` is even."""
    # Using modulo keeps this clear at the cost of a tiny bit of perf.
    return n % 2 == 0
