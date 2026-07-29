"""
email_escalation.py - Forward an unresolved query to the account manager.

Transport: SendGrid API if SENDGRID_API_KEY is set, else SMTP. Attachments
(screenshot / Excel / recording) are included. Errors are scrubbed and logged;
the caller only ever sees a generic success/failure.
"""

import base64
import smtplib
from email.message import EmailMessage

import config
from security import safe_error, logger


def _send_sendgrid(to_email, subject, body, attachments) -> bool:
    import requests
    data = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": config.ESCALATION_FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    if attachments:
        data["attachments"] = [{
            "content": base64.b64encode(content).decode(),
            "filename": name,
            "type": mime,
            "disposition": "attachment",
        } for (name, content, mime) in attachments]
    r = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {config.SENDGRID_API_KEY}",
                 "Content-Type": "application/json"},
        json=data, timeout=25,
    )
    return r.status_code in (200, 202)


def _send_smtp(to_email, subject, body, attachments) -> bool:
    msg = EmailMessage()
    msg["From"] = config.ESCALATION_FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    for name, content, mime in (attachments or []):
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(content, maintype=maintype or "application",
                           subtype=subtype or "octet-stream", filename=name)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=25) as s:
        s.starttls()
        if config.SMTP_USER:
            s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(msg)
    return True


def send_escalation(subject, body, attachments=None, to_email=None) -> tuple[bool, str]:
    """Send the escalation. Returns (ok, message)."""
    if not config.EMAIL_ENABLED:
        return False, "Email escalation isn't configured on the server yet."
    to_email = to_email or config.ACCOUNT_MANAGER_EMAIL
    try:
        if config.SENDGRID_API_KEY:
            ok = _send_sendgrid(to_email, subject, body, attachments)
        else:
            ok = _send_smtp(to_email, subject, body, attachments)
        if ok:
            logger.info("escalation sent to=%s attachments=%d", to_email, len(attachments or []))
            return True, "Sent to your account manager."
        return False, "The email service rejected the message. Please try again later."
    except Exception as e:
        ref = safe_error(e, context="escalation")
        return False, f"Couldn't send right now (ref {ref}). Please try again later."
