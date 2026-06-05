import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UserCredential:
    email: str
    role: str  # "admin" | "editor" | "guest"


def _read_secret(key: str) -> str:
    """Read a single secret from Streamlit secrets, then fall back to environment."""
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, "")


def _build_user_map() -> dict[str, tuple[str, str]]:
    """
    Returns { email: (hashed_or_raw_password, role) }.
    Reads exclusively from secrets — never from the codebase.
    """
    users = {}

    admin_email = _read_secret("ADMIN_EMAIL")
    admin_password = _read_secret("ADMIN_PASSWORD")
    if admin_email and admin_password:
        users[admin_email.lower()] = (admin_password, "admin")

    justus_email = _read_secret("JUSTUS_EMAIL")
    justus_password = _read_secret("JUSTUS_PASSWORD")
    if justus_email and justus_password:
        users[justus_email.lower()] = (justus_password, "editor")

    gast_email = _read_secret("GAST_EMAIL")
    gast_password = _read_secret("GAST_PASSWORD")
    if gast_email and gast_password:
        users[gast_email.lower()] = (gast_password, "guest")

    return users


def verify_credentials(email: str, password: str) -> UserCredential | None:
    """
    Verify email + password against secrets.
    Returns a UserCredential on success, None on failure.
    Credentials are compared in constant-time to prevent timing attacks.
    """
    import hmac

    if not email or not password:
        return None

    user_map = _build_user_map()
    stored = user_map.get(email.strip().lower())

    if stored is None:
        # Run a dummy comparison to prevent timing-based email enumeration
        hmac.compare_digest(password, "dummy")
        return None

    stored_password, role = stored
    if hmac.compare_digest(password, stored_password):
        return UserCredential(email=email.strip().lower(), role=role)

    return None


def get_openai_key() -> str:
    """Read the OpenAI API key from secrets only."""
    return _read_secret("OPENAI_API_KEY")


def has_permission(role: str, action: str) -> bool:
    """
    Role-based access control.

    Roles:
      admin  — full access
      editor — translate, TM, glossary, QA (no user/settings management)
      guest  — read-only: dashboard, TM search, glossary browse
    """
    permissions = {
        "admin":  {"dashboard", "translate", "tm", "glossary", "qa", "settings"},
        "editor": {"dashboard", "translate", "tm", "glossary", "qa"},
        "guest":  {"dashboard", "tm", "glossary"},
    }
    return action in permissions.get(role, set())
