"""
public_app.py - PUBLIC / client-facing entry point.

Runs ONLY the Query Interface (the chat). No ingestion, no dashboard, no logs
view. This is the app you expose to the internet.

Optional access control:
  - If SSO (AUTH_ENABLED) is configured -> clients must sign in.
  - Else if APP_ACCESS_PASSWORD_HASH is set -> shared-password gate.
  - Else -> open (secure the perimeter another way).
"""

import streamlit as st

import config
from auth import attempt_login

st.set_page_config(page_title="Assistant", layout="wide")


def _gate():
    if config.AUTH_ENABLED:
        if not getattr(st.user, "is_logged_in", False):
            st.title("Sign in")
            st.write("Please sign in to use the assistant.")
            st.button("Sign in", type="primary", on_click=st.login)
            st.stop()
        email = (getattr(st.user, "email", "") or "").lower()
        if config.AUTH_ALLOWED_DOMAIN and not email.endswith("@" + config.AUTH_ALLOWED_DOMAIN):
            st.error("Your account is not permitted to use this application.")
            st.button("Sign out", on_click=st.logout)
            st.stop()
        with st.sidebar:
            st.caption(f"Signed in as {email or 'user'}")
            st.button("Sign out", on_click=st.logout)
    elif config.APP_ACCESS_PASSWORD_HASH:
        if not st.session_state.get("app_ok"):
            st.title("Restricted")
            pw = st.text_input("Access password", type="password")
            if st.button("Enter"):
                ok, msg = attempt_login(st.session_state, "app", pw, config.APP_ACCESS_PASSWORD_HASH)
                if ok:
                    st.session_state.app_ok = True
                    st.rerun()
                else:
                    st.error(msg)
            st.stop()


_gate()

pg = st.navigation([st.Page("pages/1_user_chat.py", title="Assistant", default=True)])
pg.run()
