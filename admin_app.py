"""
admin_app.py - INTERNAL admin entry point.

Runs the admin side: Data Ingestion + the dashboard (usage, log, knowledge gaps,
escalations). This app should NOT be exposed to the internet — run it on an
internal port / behind the company network only. The Data Ingestion page still
enforces its own admin login as defence in depth.

Contains the client-data logs, so keep it off the public surface.
"""

import os

import streamlit as st

import config

st.set_page_config(page_title="Admin", layout="wide")


def home():
    st.title("Admin — GNB Property Assistant")
    KB_DIR = config.KB_DIR
    os.makedirs(KB_DIR, exist_ok=True)
    docs = [
        f for f in os.listdir(KB_DIR)
        if os.path.isfile(os.path.join(KB_DIR, f)) and not f.startswith(".")
    ]
    status_color = "green" if docs else "red"
    st.markdown(
        f"**Knowledge base: <span style='color:{status_color}'>"
        f"{'ONLINE' if docs else 'EMPTY'}</span>** — {len(docs)} document(s) indexed.\n\n"
        "Use **Data Ingestion** to upload documents and view the usage, log, "
        "knowledge-gap and escalation dashboards.\n\n"
        "This is the internal admin console. It is not meant to be reachable from "
        "the public internet."
    , unsafe_allow_html=True)


pages = {
    "Admin": [
        st.Page(home, title="Overview", default=True),
        st.Page("pages/0_admin_upload.py", title="Data Ingestion & Dashboard"),
    ],
}

pg = st.navigation(pages)
pg.run()
