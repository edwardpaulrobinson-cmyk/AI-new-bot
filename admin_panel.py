"""
admin_panel.py - Read-only admin views over the interaction log.

Rendered inside the (password/SSO protected) Data Ingestion page:
  - Usage (estimated, today)
  - Interaction log viewer + download
  - Knowledge gaps (what to add documents for)
  - Escalation inbox

All figures are ESTIMATES from this app's own logs, not the providers' real quota.
"""

import csv
import datetime
import io

import streamlit as st

import interaction_log

# Published free-tier reference limits (approximate, for context only).
FREE_DAILY = {
    "Gemini": "~1,500 req/day · 250k tokens/min",
    "Groq": "~14,400 req/day",
    "OpenRouter": "~50 req/day (free)",
    "Cerebras": "~1M tokens/day",
    "SambaNova": "small free tier",
}


def _today_rows(rows):
    today = datetime.date.today().isoformat()
    return [r for r in rows if (r.get("timestamp") or "").startswith(today)]


def _to_int(v):
    try:
        return int(v or 0)
    except Exception:
        return 0


def render_usage():
    st.subheader("API usage — estimated, today")
    st.caption("Estimated from this app's own logs, not the provider's real quota. "
               "Free tiers reset daily; nothing switches to paid unless you enable billing on the account.")
    rows = _today_rows(interaction_log.read_log())
    answered = [r for r in rows if r.get("status") == "answered"]

    prov = {}
    for r in answered:
        p = (r.get("provider") or "unknown").split(" ")[0]
        d = prov.setdefault(p, {"req": 0, "tin": 0, "tout": 0})
        d["req"] += 1
        d["tin"] += _to_int(r.get("tokens_in"))
        d["tout"] += _to_int(r.get("tokens_out"))

    if not prov:
        st.write("No answered questions logged today yet.")
    else:
        table = []
        for p, d in sorted(prov.items()):
            table.append({
                "Provider": p,
                "Requests today": d["req"],
                "Est. input tokens": f"{d['tin']:,}",
                "Est. output tokens": f"{d['tout']:,}",
                "Free tier (reference)": FREE_DAILY.get(p, "—"),
            })
        st.table(table)

    # feedback tally (all time)
    all_rows = interaction_log.read_log()
    up = sum(1 for r in all_rows if r.get("status") == "feedback_up")
    down = sum(1 for r in all_rows if r.get("status") == "feedback_down")
    if up or down:
        st.caption(f"Answer feedback (all time): 👍 {up}  ·  👎 {down}")


def render_log_viewer():
    st.subheader("Interaction log")
    rd = interaction_log.retention_days()
    st.caption(f"Retention: rows older than {rd} days are auto-deleted."
               if rd > 0 else
               "Retention: logs are kept indefinitely (set LOG_RETENTION_DAYS to enable auto-delete).")
    rows = interaction_log.read_log()
    if not rows:
        st.write("No interactions logged yet.")
        return

    statuses = sorted({r.get("status", "") for r in rows})
    pick = st.multiselect("Filter by status", statuses, default=statuses, key="log_status_filter")
    view = [r for r in rows if r.get("status") in pick]
    st.caption(f"Showing {min(len(view), 500)} of {len(view)} rows (newest first).")
    st.dataframe(list(reversed(view))[:500], use_container_width=True)

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=interaction_log.FIELDS)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in interaction_log.FIELDS})
    st.download_button("Download full log (CSV)", buf.getvalue(),
                       file_name="interactions.csv", mime="text/csv")

    with st.expander("Danger zone — delete all logs"):
        st.caption("Permanently deletes the entire interaction log. This cannot be undone.")
        confirm = st.checkbox("I understand this deletes everything", key="log_delete_confirm")
        if st.button("Delete all logs", disabled=not confirm):
            interaction_log.clear_all()
            st.success("All logs deleted.")
            st.rerun()


def render_knowledge_gaps():
    st.subheader("Knowledge gaps")
    st.caption("Questions the bot escalated, failed, or likely couldn't answer. "
               "These are your best candidates for new documents.")
    rows = interaction_log.read_log()
    seen, gaps = set(), []
    for r in rows:
        q = (r.get("question") or "").strip()
        a = (r.get("answer") or "").lower()
        status = r.get("status")
        is_gap = (status in ("escalated", "failed")
                  or "couldn't find that" in a
                  or "could not find that" in a)
        if q and is_gap and q.lower() not in seen:
            seen.add(q.lower())
            reason = {"escalated": "escalated to account manager",
                      "failed": "no provider answered"}.get(status, "not found in documents")
            gaps.append((q, reason))

    if not gaps:
        st.write("No gaps detected yet — the bot has answered everything from your documents.")
        return
    st.write(f"**{len(gaps)}** distinct question(s) worth adding documentation for:")
    for q, reason in gaps[:200]:
        st.markdown(f"- {q}  \n  _{reason}_")


def render_escalations():
    st.subheader("Escalation inbox")
    rows = [r for r in interaction_log.read_log() if r.get("status") == "escalated"]
    if not rows:
        st.write("No escalations yet.")
        return
    st.caption(f"{len(rows)} escalation(s) sent to account managers.")
    for r in reversed(rows):
        with st.container(border=True):
            st.markdown(f"**{r.get('timestamp', '')}** → {r.get('escalated_to', '')}")
            st.markdown(f"**Q:** {r.get('question', '')}")
            if r.get("message"):
                st.caption(f"Message: {r.get('message')}")


def render_all():
    interaction_log.prune_old()   # enforce retention whenever an admin opens the dashboard
    tabs = st.tabs(["Usage", "Log", "Knowledge gaps", "Escalations"])
    with tabs[0]:
        render_usage()
    with tabs[1]:
        render_log_viewer()
    with tabs[2]:
        render_knowledge_gaps()
    with tabs[3]:
        render_escalations()
