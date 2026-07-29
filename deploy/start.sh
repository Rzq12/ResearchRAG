#!/usr/bin/env bash
# Launch Streamlit + FastAPI + nginx in one container so a single HF Space
# (or Railway service) serves both the existing Streamlit UI and the REST API
# the React frontend calls. Streamlit itself is run exactly as before, just on
# an internal port behind nginx.
set -euo pipefail

# Declared before the trap so a signal arriving early cannot reference an unset
# variable under `set -u`.
nginx_pid=""
uvicorn_pid=""
streamlit_pid=""

# Public port: Railway injects $PORT; HF Spaces uses the Dockerfile app_port.
export NGINX_PORT="${PORT:-8501}"

# Render the nginx config with the chosen port.
envsubst '${NGINX_PORT}' < /app/deploy/nginx.conf.template > /etc/nginx/conf.d/default.conf

# Refuse to start on a bad proxy config rather than failing later under traffic.
nginx -t

# FastAPI (internal) — the API surface for the React app.
uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1 &
uvicorn_pid=$!

# Streamlit (internal) — the original app, unchanged.
# XSRF protection stays ON: this origin is publicly reachable through nginx.
# CORS is disabled because Streamlit is same-origin here (the React app talks
# to /api/* instead, which has its own explicit allowlist).
streamlit run streamlit_app.py \
    --server.address=127.0.0.1 \
    --server.port=8503 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=true &
streamlit_pid=$!

# Take the whole container down if ANY service dies, so the platform's restart
# policy can recover it. Without this a dead API would linger behind a healthy
# looking Streamlit.
shutdown() {
    trap - SIGINT SIGTERM
    for pid in "$nginx_pid" "$uvicorn_pid" "$streamlit_pid"; do
        [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
    done
}
trap shutdown SIGINT SIGTERM

# nginx on the public port.
nginx -g 'daemon off;' &
nginx_pid=$!

# Wait for whichever process exits first, then tear the rest down.
wait -n
status=$?
shutdown
exit "$status"
