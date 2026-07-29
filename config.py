"""
config.py - Single source of truth for configuration and secrets.

SECURITY MODEL
--------------
* Secrets are read from the environment, and support the Docker/K8s "*_FILE"
  convention: if e.g. GROQ_API_KEY_FILE points to a mounted secret file, its
  contents are used. This lets you use real secret stores instead of a flat .env.
* On Streamlit Community Cloud, secrets live in st.secrets (not env vars), so
  get_secret() falls back to st.secrets last. Order: *_FILE > env var > st.secrets.
* Secret VALUES never leave the server and are never logged or printed here.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    pass


_ST_SECRETS = None
_ST_SECRETS_TRIED = False


def _st_secret(name: str):
    """Look a value up in Streamlit's secrets store, if one is configured
    (Streamlit Community Cloud). Cached so we don't repeatedly hit a missing
    secrets file. Returns a string or None."""
    global _ST_SECRETS, _ST_SECRETS_TRIED
    if not _ST_SECRETS_TRIED:
        _ST_SECRETS_TRIED = True
        try:
            import streamlit as st
            _ = st.secrets  # raises if no secrets are configured
            _ST_SECRETS = st.secrets
        except Exception:
            _ST_SECRETS = None
    if _ST_SECRETS is None:
        return None
    try:
        if name in _ST_SECRETS:
            v = _ST_SECRETS[name]
            return str(v) if v is not None else None
    except Exception:
        return None
    return None


def get_secret(name: str) -> str | None:
    """Return a secret from a mounted file (NAME_FILE), an env var (NAME), or
    Streamlit's secrets store. File takes precedence (Docker/K8s secrets win),
    then env vars, then st.secrets (Streamlit Community Cloud)."""
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
        except Exception:
            pass
    val = os.environ.get(name)
    if val and val.strip():
        return val.strip()
    # Streamlit Community Cloud keeps secrets in st.secrets, not environment vars.
    sv = _st_secret(name)
    return sv.strip() if sv else None


# --- LLM provider keys ---
PROVIDER_ENV = {
    "Cerebras": "CEREBRAS_API_KEY",
    "Groq": "GROQ_API_KEY",
    "SambaNova": "SAMBANOVA_API_KEY",
    "OpenRouter": "OPENROUTER_API_KEY",
    "Gemini": "GEMINI_API_KEY",
}


def provider_keys() -> dict:
    return {p: get_secret(env) for p, env in PROVIDER_ENV.items() if get_secret(env)}


# --- Auth: password fallback ---
ADMIN_PASSWORD_HASH = get_secret("ADMIN_PASSWORD_HASH")
APP_ACCESS_PASSWORD_HASH = get_secret("APP_ACCESS_PASSWORD_HASH")

# --- Auth: SSO / OIDC (optional, preferred for production) ---
AUTH_CLIENT_ID = get_secret("AUTH_CLIENT_ID")
AUTH_CLIENT_SECRET = get_secret("AUTH_CLIENT_SECRET")
AUTH_COOKIE_SECRET = get_secret("AUTH_COOKIE_SECRET")
AUTH_REDIRECT_URI = get_secret("AUTH_REDIRECT_URI")
AUTH_SERVER_METADATA_URL = get_secret("AUTH_SERVER_METADATA_URL")
AUTH_ALLOWED_DOMAIN = (get_secret("AUTH_ALLOWED_DOMAIN") or "").lower().lstrip("@")

# Comma-separated list of emails that are admins when signed in via SSO.
ADMIN_EMAILS = {
    e.strip().lower()
    for e in (get_secret("ADMIN_EMAILS") or "").split(",")
    if e.strip()
}

# SSO is considered configured only when every required piece is present.
AUTH_ENABLED = all([
    AUTH_CLIENT_ID, AUTH_CLIENT_SECRET, AUTH_COOKIE_SECRET,
    AUTH_REDIRECT_URI, AUTH_SERVER_METADATA_URL,
])


def all_secret_values() -> list:
    """Every secret value currently set - used ONLY to scrub logs."""
    names = list(PROVIDER_ENV.values()) + [
        "ADMIN_PASSWORD_HASH", "APP_ACCESS_PASSWORD_HASH",
        "AUTH_CLIENT_ID", "AUTH_CLIENT_SECRET", "AUTH_COOKIE_SECRET",
        "SENDGRID_API_KEY", "SMTP_PASSWORD",
    ]
    vals = [get_secret(n) for n in names]
    return [v for v in vals if v]


# --- Limits ---
KB_DIR = os.environ.get("KB_DIR", "knowledge_base")
# Always-on baseline document (included in every answer, excluded from the index).
BASE_CONTEXT_FILE = os.environ.get("BASE_CONTEXT_FILE", "GNB_CRM_Baseline.md")
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt", "md", "csv", "xlsx", "xlsm", "pptx", "html", "htm",
}
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
MAX_KB_TOTAL_MB = int(os.environ.get("MAX_KB_TOTAL_MB", "200"))
MAX_QUESTIONS_PER_MIN = int(os.environ.get("MAX_QUESTIONS_PER_MIN", "20"))
MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "300"))

# --- Attachments (screenshots / Excel / voice) ---
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "webm"}
DATA_EXTENSIONS = {"xlsx", "xlsm", "xls", "csv", "txt", "md", "pdf", "docx"}
MAX_ATTACH_MB = int(os.environ.get("MAX_ATTACH_MB", "20"))

# --- Escalation to account manager (email) ---
ACCOUNT_MANAGER_EMAIL = get_secret("ACCOUNT_MANAGER_EMAIL")
ESCALATION_FROM_EMAIL = get_secret("ESCALATION_FROM_EMAIL")
SENDGRID_API_KEY = get_secret("SENDGRID_API_KEY")
SMTP_HOST = get_secret("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = get_secret("SMTP_USER")
SMTP_PASSWORD = get_secret("SMTP_PASSWORD")
# Email escalation is available only when a recipient and a transport are set.
EMAIL_ENABLED = bool(ACCOUNT_MANAGER_EMAIL and ESCALATION_FROM_EMAIL and (SENDGRID_API_KEY or SMTP_HOST))
