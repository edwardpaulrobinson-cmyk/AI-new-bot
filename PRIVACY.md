# Privacy & data handling

Plain-English record of what this system stores, for how long, and who can see it.
Review with whoever owns data protection before real client data flows through it.

## What is stored

**Knowledge base** (`knowledge_base/`): the documents an admin uploads. Whatever
you put in here is what the assistant can answer from. Don't upload anything you
wouldn't want the assistant to surface.

**Interaction log** (`logs/interactions.csv`): one row per event. Fields:
`timestamp, user, mode, provider, status, question, answer, tokens_in, tokens_out,
escalated_to, message`. In practice this means we store **the questions people ask
and the answers given** — which may contain personal data (names, addresses,
property or tenancy details). Treat this log as personal data.

**We do not** store passwords (only a bcrypt hash of the admin password), and API
keys live in the environment/secret store, never in the log.

## Retention

- Log rows are auto-deleted after `LOG_RETENTION_DAYS` days (default **90**).
  Set it in `.env`; set to `0` to keep indefinitely (not recommended for client data).
- Pruning runs whenever an admin opens the dashboard.
- An admin can also delete the entire log at any time (Data Ingestion → Log →
  "Danger zone").

## Who can access it

- The **interaction log and dashboards live only in the internal admin app**
  (`admin_app.py`), which is **not exposed to the internet** — it binds to
  localhost and is reached via VPN/SSH only.
- The **public app** (`public_app.py`) that clients use has **no** access to the
  log or upload pages at all.
- The admin area additionally requires an admin login (bcrypt password or an
  allow-listed SSO identity).

## Your responsibilities (operator)

1. Set a sensible `LOG_RETENTION_DAYS` and confirm it matches your data-protection
   policy.
2. Keep the admin app off the public internet (the provided `docker-compose.yml`
   binds it to `127.0.0.1` — don't change that to a public port).
3. Back up the `logs` and `knowledge_base` volumes securely; treat backups as
   personal data too.
4. Have a process to honour data-subject requests (find/delete a person's entries
   in the log if asked). The CSV is searchable; deletion can be done by editing
   the file or clearing the log.
5. Tell staff/clients, where appropriate, that their questions are logged for
   quality and support.

## Minimising what's logged (optional)

If you'd rather not store full question/answer text, that can be changed to log
only metadata (timestamp, provider, outcome) — ask and it's a small adjustment.
