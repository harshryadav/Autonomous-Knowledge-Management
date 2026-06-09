"""Signup endpoint: creates an account and a first session."""

import auth_session


def signup(username, password):
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    return auth_session.create_session(username, role="member")
