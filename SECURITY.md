# Security posture

This document states exactly what the application protects and what remains the
operator's responsibility. "No leakage" is a shared outcome: the app secures the
code layer; you must secure the host and transport layer.

## What the application guarantees (code layer)

- **Secrets live in the environment only.** All API keys and password hashes are
  read from environment variables (`config.py`), populated from `.env` in dev or
  a secrets manager in production. No secret is hardcoded anywhere in the repo.
- **Secrets never reach the browser.** Keys are used only server-side to build
  API clients. They are never rendered, never sent to the client, never in HTML.
- **Secrets never reach logs or error screens.** All exceptions pass through
  `security.safe_error()`, which logs a *scrubbed* detail server-side and shows
  the user only a random reference id. `scrub_secrets()` replaces any live key
  value (and token-looking strings) with `[REDACTED]`.
- **Admin is password-protected with bcrypt.** The Data Ingestion page requires a
  password verified against a bcrypt hash (`ADMIN_PASSWORD_HASH`). The plaintext
  is never stored. Login attempts are throttled and locked after repeated fails.
- **Optional whole-app gate.** Set `APP_ACCESS_PASSWORD_HASH` to lock every page.
- **Upload hardening.** Filenames are sanitised (path-traversal blocked), types
  are allow-listed, per-file and total-size caps enforced, and the write path is
  verified to stay inside the knowledge-base directory.
- **Abuse control.** Per-session question rate limiting caps cost/DoS exposure.
- **Secure Streamlit config.** XSRF protection on, usage stats off, browser
  error details off, non-root container user.

## What YOU must do (host / transport layer)

1. **TLS is mandatory.** Put real certificates in `nginx/certs/`
   (`fullchain.pem`, `privkey.pem`) — use Let's Encrypt/certbot. Never run the
   query interface over plain HTTP in production.
2. **Never commit `.env`.** It is git-ignored; keep it that way. Prefer a real
   secrets manager (Docker secrets, AWS/GCP Secrets Manager, Vault) over a file.
3. **Rotate any key that has ever been exposed** (your earlier Gemini key was
   reported leaked — rotate it before go-live).
4. **Restrict the host.** Only expose ports 80/443 via nginx; the app container
   is internal (`expose`, not `ports`). Keep the OS patched and firewalled.
5. **Rate limiting is per-process.** For multiple app instances behind a load
   balancer, move rate-limit + login-attempt state to a shared store (Redis).
6. **Back up** the `kb_data` volume; treat uploaded documents as sensitive data.

## Residual notes

- Streamlit is a single-tenant app framework, not a hardened multi-tenant SaaS
  platform. For true per-customer isolation you would run separate instances or
  add an identity provider (SSO/OIDC) in front.
- The RAG cache (`.rag_cache.pkl`) may contain document text; it lives on the
  server volume only and is git-ignored.

## Update: SSO/OIDC and Docker secrets
- **SSO/OIDC** (`st.login`) is supported. When configured, identity is handled by
  your IdP; the app trusts a signed cookie and can restrict by email domain.
  Admin rights can be tied to SSO identity via `ADMIN_EMAILS` (no shared password).
- **Docker secrets**: every secret can be supplied via a mounted file using the
  `<NAME>_FILE` convention, so nothing sensitive need sit in a flat `.env`. The
  OIDC client secret and cookie secret are written to an in-container
  `secrets.toml` (mode 600) at startup and are never committed.
- **Cookie secret** must be a strong random value and rotated periodically; it
  signs the auth cookie.
