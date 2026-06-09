"""Login endpoint: exchanges credentials for a session token."""

import auth_session

_FAKE_USERS = {"ada": "member", "grace": "admin"}


def login(username, password):
    if username not in _FAKE_USERS or not password:
        raise auth_session.AuthError("Invalid credentials")
    return auth_session.create_session(username, role=_FAKE_USERS[username])
