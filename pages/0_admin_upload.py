import os
import sys

import streamlit as st

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
import admin_panel
from auth import attempt_login
from security import sanitize_filename, allowed_extension, safe_error, logger
from utils import parse_file

st.set_page_config(page_title="Data Ingestion", layout="wide")

KB_DIR = config.KB_DIR
os.makedirs(KB_DIR, exist_ok=True)

st.title("DATA INGESTION")


# --- Admin access: SSO identity (ADMIN_EMAILS) OR bcrypt password ---
def _is_sso_admin() -> bool:
    if not (config.AUTH_ENABLED and config.ADMIN_EMAILS):
        return False
    if not getattr(st.user, "is_logged_in", False):
        return False
    return (getattr(st.user, "email", "") or "").lower() in config.ADMIN_EMAILS


if not _is_sso_admin():
    if not config.ADMIN_PASSWORD_HASH:
        st.error("Admin area is not configured. Set ADMIN_PASSWORD_HASH, or add your "
                 "email to ADMIN_EMAILS and sign in via SSO.")
        st.stop()
    if not st.session_state.get("admin_ok"):
        st.info("Restricted area. Enter the admin password.")
        pw = st.text_input("Admin password", type="password")
        if st.button("Unlock"):
            ok, msg = attempt_login(st.session_state, "admin", pw, config.ADMIN_PASSWORD_HASH)
            if ok:
                st.session_state.admin_ok = True
                st.rerun()
            else:
                st.error(msg)
        st.stop()

st.success("Authenticated as admin.")
st.markdown(f"Allowed types: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}. "
            f"Max {config.MAX_UPLOAD_MB} MB per file.")


def kb_total_bytes():
    total = 0
    for f in os.listdir(KB_DIR):
        p = os.path.join(KB_DIR, f)
        if os.path.isfile(p):
            total += os.path.getsize(p)
    return total


# --- Upload with validation ---
uploaded_files = st.file_uploader(
    "Drop files here",
    type=sorted(config.ALLOWED_EXTENSIONS),
    accept_multiple_files=True,
)

if uploaded_files:
    for uf in uploaded_files:
        safe_name = sanitize_filename(uf.name)
        if not allowed_extension(safe_name):
            st.error(f"Rejected {uf.name}: file type not allowed.")
            continue
        size_mb = uf.size / (1024 * 1024)
        if size_mb > config.MAX_UPLOAD_MB:
            st.error(f"Rejected {uf.name}: {size_mb:.1f} MB exceeds {config.MAX_UPLOAD_MB} MB limit.")
            continue
        if kb_total_bytes() + uf.size > config.MAX_KB_TOTAL_MB * 1024 * 1024:
            st.error(f"Rejected {uf.name}: knowledge base would exceed {config.MAX_KB_TOTAL_MB} MB total.")
            continue
        dest = os.path.join(KB_DIR, safe_name)
        if os.path.commonpath([os.path.abspath(dest), os.path.abspath(KB_DIR)]) != os.path.abspath(KB_DIR):
            st.error(f"Rejected {uf.name}: invalid path.")
            continue
        try:
            with open(dest, "wb") as f:
                f.write(uf.getbuffer())
            preview = parse_file(dest).strip()
            logger.info("admin upload name=%s bytes=%s", safe_name, uf.size)
            if preview:
                st.success(f"Saved & parsed: {safe_name} ({len(preview):,} chars extracted)")
            else:
                st.warning(f"Saved: {safe_name} (no text extracted - may be scanned/image)")
        except Exception as e:
            ref = safe_error(e, context="upload")
            st.error(f"Could not save {safe_name}. Reference: {ref}")

st.divider()

# --- Manage existing documents ---
docs = sorted(
    f for f in os.listdir(KB_DIR)
    if os.path.isfile(os.path.join(KB_DIR, f)) and not f.startswith(".")
)
st.subheader(f"Indexed documents ({len(docs)})")
if not docs:
    st.write("No documents yet.")
else:
    for d in docs:
        path = os.path.join(KB_DIR, d)
        size_kb = os.path.getsize(path) / 1024
        c1, c2, c3 = st.columns([6, 2, 1])
        c1.write(f"**{d}**")
        c2.write(f"{size_kb:,.1f} KB")
        if c3.button("Delete", key=f"del_{d}"):
            try:
                os.remove(path)
                logger.info("admin delete name=%s", d)
            except Exception as e:
                safe_error(e, context="delete")
            st.rerun()

st.divider()

# --- Admin dashboard: usage, log, knowledge gaps, escalations ---
st.header("Admin dashboard")
admin_panel.render_all()

st.divider()
if st.button("Log out"):
    st.session_state.admin_ok = False
    st.rerun()
