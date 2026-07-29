"""
security.py - Input hardening, error scrubbing, and rate limiting.

None of these functions ever emit a secret. safe_error() actively strips any
known secret value out of text before it is logged, as a defence in depth.
"""

import logging
import os
import re
import time
import uuid

import config

logger = logging.getLogger("docbot")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# --- Filenames ---------------------------------------------------------------
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(name: str) -> str:
    """Strip any directory components and unsafe characters (blocks path
    traversal like ../../etc/passwd and hidden dotfiles)."""
    name = os.path.basename(name or "")
    name = name.replace("\x00", "")
    name = _SAFE_NAME.sub("_", name)
    name = name.lstrip(".") or "file"
    return name[:120]


def allowed_extension(name: str) -> bool:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    return ext in config.ALLOWED_EXTENSIONS


# --- Error handling ----------------------------------------------------------
def scrub_secrets(text: str) -> str:
    """Replace any live secret value found in text with [REDACTED]."""
    if not text:
        return text
    for secret in config.all_secret_values():
        if secret and secret in text:
            text = text.replace(secret, "[REDACTED]")
    # Also mask anything that looks like a bearer/sk- style token.
    text = re.sub(r"\b(sk|rk|key|api|bearer)[-_][A-Za-z0-9]{8,}\b", "[REDACTED]", text, flags=re.I)
    return text


def safe_error(exc: Exception, context: str = "") -> str:
    """Log the (scrubbed) technical detail server-side; return a generic,
    secret-free reference the UI can safely show."""
    ref = uuid.uuid4().hex[:8]
    detail = scrub_secrets(f"{type(exc).__name__}: {exc}")
    logger.error("ref=%s ctx=%s %s", ref, context, detail)
    return ref


# --- Rate limiting (per user session) ---------------------------------------
def check_rate_limit(session_state, key="q_times", max_events=None, window=60) -> bool:
    """Simple sliding-window limiter. Returns True if the action is allowed.
    NOTE: state is per app-process; for multi-instance deploys use a shared
    store (Redis). Documented in SECURITY.md."""
    max_events = max_events or config.MAX_QUESTIONS_PER_MIN
    now = time.time()
    times = [t for t in session_state.get(key, []) if now - t < window]
    if len(times) >= max_events:
        session_state[key] = times
        return False
    times.append(now)
    session_state[key] = times
    return True
