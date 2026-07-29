"""
auth.py - Password verification with bcrypt + brute-force throttling.

Passwords are NEVER stored. Only a bcrypt hash lives in the environment
(ADMIN_PASSWORD_HASH / APP_ACCESS_PASSWORD_HASH). Verification is constant-time
via bcrypt.checkpw.
"""

import time

import bcrypt

import config
from security import logger


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not password or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def _throttled(session_state, bucket: str) -> float:
    """Return remaining lockout seconds (0 if not locked)."""
    locked_until = session_state.get(f"{bucket}_locked_until", 0)
    remaining = locked_until - time.time()
    return max(0.0, remaining)


def attempt_login(session_state, bucket: str, password: str, stored_hash: str | None) -> tuple[bool, str]:
    """Verify a password with attempt throttling.

    Returns (ok, message). On too many failures, locks the bucket for a cooldown.
    """
    remaining = _throttled(session_state, bucket)
    if remaining > 0:
        return False, f"Too many attempts. Try again in {int(remaining)}s."

    if verify_password(password, stored_hash):
        session_state[f"{bucket}_fails"] = 0
        logger.info("auth success bucket=%s", bucket)
        return True, "ok"

    fails = session_state.get(f"{bucket}_fails", 0) + 1
    session_state[f"{bucket}_fails"] = fails
    logger.info("auth failure bucket=%s fails=%s", bucket, fails)
    if fails >= config.MAX_LOGIN_ATTEMPTS:
        session_state[f"{bucket}_locked_until"] = time.time() + config.LOGIN_LOCKOUT_SECONDS
        session_state[f"{bucket}_fails"] = 0
        return False, f"Too many attempts. Locked for {config.LOGIN_LOCKOUT_SECONDS // 60} min."
    return False, "Incorrect password."
