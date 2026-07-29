# Document AI Bot - Production

A Streamlit chatbot that answers questions over your own documents, hardened for
server hosting. See `SECURITY.md` for the full security posture.

## Features
- Multi-provider "waterfall" LLM router (Cerebras -> Groq -> SambaNova ->
  OpenRouter -> Gemini) with automatic failover.
- Two answer modes: **Full context** or **Smart retrieval (RAG)** (semantic when
  a Gemini key is present, keyword fallback otherwise).
- All secrets from environment; bcrypt admin login; upload + rate-limit hardening.
- Docker + nginx/TLS deployment.

## 1. Configure secrets
```bash
cp .env.example .env
python scripts/hash_password.py     # generates ADMIN_PASSWORD_HASH
# edit .env: paste the hash and at least one provider API key
```

## 2. Run locally (dev)
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 3. Deploy with Docker + TLS (production)
```bash
# put TLS certs in nginx/certs/ as fullchain.pem and privkey.pem
docker compose up -d --build
```
- App is reachable only through nginx on 443 (HTTP 80 redirects to HTTPS).
- Documents persist in the `kb_data` volume.
- Secrets come from `.env` at runtime (never baked into the image).

## 4. Use it
- **Query Interface** - ask questions (public unless you set APP_ACCESS_PASSWORD_HASH).
- **Data Ingestion** - admin-only; unlock with your admin password, upload docs.

## Roadmap to scale
1. Move rate-limit/login state to Redis for multi-instance deployments.
2. Move the vector index to a hosted store (pgvector/Pinecone) for persistence
   and sharing across instances.
3. Add a paid provider to the waterfall for guaranteed throughput.
4. Front with SSO/OIDC for per-user identity.

## SSO / OIDC login (optional, recommended)
Configure an OIDC app with your provider (Google/Microsoft/Okta/Auth0), then set
`AUTH_CLIENT_ID`, `AUTH_CLIENT_SECRET`, `AUTH_COOKIE_SECRET`, `AUTH_REDIRECT_URI`,
and `AUTH_SERVER_METADATA_URL` (see `.env.example`). When these are present:
- The whole app requires sign-in (via `st.login()`); no password gate needed.
- Restrict access to your company with `AUTH_ALLOWED_DOMAIN=yourdomain.com`.
- Make specific people admins with `ADMIN_EMAILS=alice@you.com,bob@you.com` —
  they get the Data Ingestion page without a separate password.

The container's `entrypoint.sh` renders `.streamlit/secrets.toml` from these
environment variables at startup, so the OIDC client secret still lives only in
your environment / secret store, never in the repo.

## Using Docker secrets instead of .env
For the strongest secret handling, use mounted secret files:
```bash
# put each value in ./secrets/<name>.txt (git-ignored)
docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d --build
```
`config.py` reads any secret from `<NAME>_FILE` before falling back to `<NAME>`,
so Docker/Kubernetes secrets take precedence over plain env vars.
