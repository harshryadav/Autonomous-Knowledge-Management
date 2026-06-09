"""Session management: tokens, expiry, and permission checks."""

import hashlib
import time

SESSION_TTL_SECONDS = 3600
ADMIN_ROLES = {"admin", "superuser"}

_sessions = {}


class AuthError(Exception):
    """Raised on invalid credentials or expired sessions."""


def _token_for(user_id, issued_at):
    raw = f"{user_id}:{issued_at}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def create_session(user_id, role="member"):
    issued_at = time.time()
    token = _token_for(user_id, issued_at)
    _sessions[token] = {
        "user_id": user_id,
        "role": role,
        "issued_at": issued_at,
        "expires_at": issued_at + SESSION_TTL_SECONDS,
    }
    return token


def validate_session(token):
    session = _sessions.get(token)
    if session is None:
        raise AuthError("Unknown session token")
    if time.time() > session["expires_at"]:
        del _sessions[token]
        raise AuthError("Session expired")
    return session


def refresh_session(token):
    session = validate_session(token)
    session["expires_at"] = time.time() + SESSION_TTL_SECONDS
    return session


def end_session(token):
    _sessions.pop(token, None)


def require_role(token, *roles):
    session = validate_session(token)
    if session["role"] not in roles:
        raise AuthError(
            f"Role '{session['role']}' lacks permission (needs one of {roles})"
        )
    return session


def is_admin(token):
    try:
        session = validate_session(token)
    except AuthError:
        return False
    return session["role"] in ADMIN_ROLES


def active_session_count():
    now = time.time()
    return sum(1 for s in _sessions.values() if s["expires_at"] > now)
