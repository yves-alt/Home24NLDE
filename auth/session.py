import streamlit as st
from auth.credentials import verify_credentials, has_permission, UserCredential


SESSION_KEY = "_auth_user"


def is_authenticated() -> bool:
    return SESSION_KEY in st.session_state and st.session_state[SESSION_KEY] is not None


def current_user() -> UserCredential | None:
    return st.session_state.get(SESSION_KEY)


def current_role() -> str:
    user = current_user()
    return user.role if user else "guest"


def can(action: str) -> bool:
    return has_permission(current_role(), action)


def login(email: str, password: str) -> bool:
    user = verify_credentials(email, password)
    if user:
        st.session_state[SESSION_KEY] = user
        return True
    return False


def logout():
    st.session_state.pop(SESSION_KEY, None)


def require_auth():
    """Call at the top of any page that requires login. Stops execution if not authenticated."""
    if not is_authenticated():
        st.stop()


def require_permission(action: str):
    """Stop execution if the current user lacks the required permission."""
    if not can(action):
        st.error("You do not have permission to access this page.")
        st.stop()
