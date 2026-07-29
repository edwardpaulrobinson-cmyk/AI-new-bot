#!/bin/sh
set -e

# Which app + port this container runs (set per service in docker-compose).
APP_FILE="${APP_FILE:-public_app.py}"
PORT="${PORT:-8501}"

SECRETS_DIR="/app/.streamlit"
mkdir -p "$SECRETS_DIR"

read_secret() {
  eval "val=\${$1:-}"
  eval "file=\${${1}_FILE:-}"
  if [ -n "$file" ] && [ -f "$file" ]; then
    cat "$file"
  else
    printf '%s' "$val"
  fi
}

CID=$(read_secret AUTH_CLIENT_ID)
CSEC=$(read_secret AUTH_CLIENT_SECRET)
COOK=$(read_secret AUTH_COOKIE_SECRET)

if [ -n "$CID" ] && [ -n "$CSEC" ] && [ -n "$COOK" ] && \
   [ -n "${AUTH_REDIRECT_URI:-}" ] && [ -n "${AUTH_SERVER_METADATA_URL:-}" ]; then
  umask 077
  cat > "$SECRETS_DIR/secrets.toml" <<TOML
[auth]
redirect_uri = "${AUTH_REDIRECT_URI}"
cookie_secret = "${COOK}"
client_id = "${CID}"
client_secret = "${CSEC}"
server_metadata_url = "${AUTH_SERVER_METADATA_URL}"
TOML
  echo "[entrypoint] OIDC auth configured."
else
  rm -f "$SECRETS_DIR/secrets.toml" 2>/dev/null || true
  echo "[entrypoint] OIDC not configured; using password/open gate."
fi

echo "[entrypoint] starting $APP_FILE on port $PORT"
exec streamlit run "$APP_FILE" \
  --server.port="$PORT" --server.address=0.0.0.0 --server.headless=true
