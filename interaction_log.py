"""
interaction_log.py - Append-only audit log of questions, answers, and outcomes.

Each event is one row in logs/interactions.csv (openable in Excel):
  timestamp, user, mode, provider, status, question, answer,
  tokens_in, tokens_out, escalated_to, message

status values:
  answered      - the AI produced an answer
  failed        - all providers failed
  sorted        - user marked the answer resolved
  escalated     - user forwarded the query to an account manager
  feedback_up   - user gave a thumbs up
  feedback_down - user gave a thumbs down
"""

import csv
import datetime
import os
import threading

LOG_DIR = os.environ.get("LOG_DIR", "logs")
LOG_FILE = os.path.join(LOG_DIR, "interactions.csv")
_LOCK = threading.Lock()

FIELDS = ["timestamp", "user", "mode", "provider", "status",
          "question", "answer", "tokens_in", "tokens_out", "escalated_to", "message"]


def _header_matches():
    """True if the existing file's header matches the current schema."""
    try:
        with open(LOG_FILE, "r", newline="", encoding="utf-8") as f:
            return f.readline().strip() == ",".join(FIELDS)
    except Exception:
        return True


def log_event(status, question="", answer="", user="", mode="", provider="",
              tokens_in=0, tokens_out=0, escalated_to="", message=""):
    """Append one event to the CSV log. Never raises - logging must not break the app."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        row = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "user": user or "local",
            "mode": mode,
            "provider": provider,
            "status": status,
            "question": question,
            "answer": answer,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "escalated_to": escalated_to,
            "message": message,
        }
        with _LOCK:
            # If the schema changed since the file was created, rotate the old
            # file aside (kept as .bak) so we never mix column layouts.
            if os.path.exists(LOG_FILE) and not _header_matches():
                try:
                    os.replace(LOG_FILE, LOG_FILE + ".bak")
                except Exception:
                    pass
            is_new = not os.path.exists(LOG_FILE)
            with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if is_new:
                    w.writeheader()
                w.writerow(row)
    except Exception:
        pass


def read_log():
    """Return all logged rows as a list of dicts (newest last). Never raises."""
    rows = []
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    # Normalise to the current schema: only known fields, blanks
                    # for anything missing (prevents NaN / broken table rendering).
                    rows.append({k: (r.get(k) or "") for k in FIELDS})
    except Exception:
        pass
    return rows


def retention_days():
    """How long log rows are kept. 0 = keep forever. Set via LOG_RETENTION_DAYS."""
    try:
        return int(os.environ.get("LOG_RETENTION_DAYS", "90"))
    except Exception:
        return 90


def prune_old(days=None):
    """Delete log rows older than `days`. Returns the number removed. Never raises."""
    try:
        days = retention_days() if days is None else days
        if days <= 0:
            return 0
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        rows = read_log()
        if not rows:
            return 0
        kept = [r for r in rows if (r.get("timestamp") or "") >= cutoff]
        removed = len(rows) - len(kept)
        if removed:
            with _LOCK:
                with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=FIELDS)
                    w.writeheader()
                    for r in kept:
                        w.writerow({k: r.get(k, "") for k in FIELDS})
        return removed
    except Exception:
        return 0


def clear_all():
    """Delete the entire log. Never raises."""
    try:
        with _LOCK:
            if os.path.exists(LOG_FILE):
                os.remove(LOG_FILE)
        return True
    except Exception:
        return False
