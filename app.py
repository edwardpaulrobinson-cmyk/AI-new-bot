"""
app.py - Entry point / navigation hub (production).

Access control precedence:
  1. If SSO/OIDC is configured (AUTH_ENABLED) -> require sign-in via st.login().
  2. Else if APP_ACCESS_PASSWORD_HASH is set -> shared-password gate.
  3. Else -> open app.

Note: the home page is defined as a function and registered with st.Page(home).
We do NOT register the entry file as a page pointing to itself, because newer
Streamlit versions re-enter the entry script and terminate the server.
"""

import os

import streamlit as st

import config
from auth import attempt_login

st.set_page_config(page_title="System Hub", layout="wide")


def _sso_gate() -> None:
    if not getattr(st.user, "is_logged_in", False):
        st.title("Sign in")
        st.write("Please sign in with your organisation account to continue.")
        st.button("Sign in with SSO", type="primary", on_click=st.login)
        st.stop()
    email = (getattr(st.user, "email", "") or "").lower()
    if config.AUTH_ALLOWED_DOMAIN and not email.endswith("@" + config.AUTH_ALLOWED_DOMAIN):
        st.error("Your account is not permitted to access this application.")
        st.button("Sign out", on_click=st.logout)
        st.stop()
    with st.sidebar:
        st.caption(f"Signed in as {email or 'user'}")
        st.button("Sign out", on_click=st.logout)


def _password_gate() -> None:
    if st.session_state.get("app_ok"):
        return
    st.title("Restricted")
    st.caption("Enter the access password to continue.")
    pw = st.text_input("Access password", type="password")
    if st.button("Enter"):
        ok, msg = attempt_login(st.session_state, "app", pw, config.APP_ACCESS_PASSWORD_HASH)
        if ok:
            st.session_state.app_ok = True
            st.rerun()
        else:
            st.error(msg)
    st.stop()


def app_gate() -> None:
    if config.AUTH_ENABLED:
        _sso_gate()
    elif config.APP_ACCESS_PASSWORD_HASH:
        _password_gate()
    # else: open app


def home() -> None:
    """The System Terminal home page."""
    KB_DIR = config.KB_DIR
    os.makedirs(KB_DIR, exist_ok=True)
    docs = [
        f for f in os.listdir(KB_DIR)
        if os.path.isfile(os.path.join(KB_DIR, f)) and not f.startswith(".")
    ]
    doc_count = len(docs)
    status_color = "green" if doc_count > 0 else "red"
    st.title("System Terminal")
    st.markdown(
        f"**STATUS: <span style='color:{status_color}'>"
        f"{'ONLINE' if doc_count > 0 else 'EMPTY'}</span>**\n\n"
        f"Currently Indexing: **{doc_count} Documents**\n\n"
        "Welcome to the core interface. Use the sidebar to navigate.\n\n"
        "- **Data Ingestion:** Upload and parse knowledge base documents (admin only).\n"
        "- **Query Interface:** Ask questions across the knowledge base."
    , unsafe_allow_html=True)


app_gate()

pages = {
    "Hub": [st.Page(home, title="System Terminal", default=True)],
    "Portals": [
        st.Page("pages/1_user_chat.py", title="Query Interface"),
        st.Page("pages/0_admin_upload.py", title="Data Ingestion"),
    ],
}

pg = st.navigation(pages)
pg.run()
