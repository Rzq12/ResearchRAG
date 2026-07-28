#!/usr/bin/env bash
# Launch Streamlit + FastAPI + nginx in one container so a single HF Space
# (or Railway service) serves both the existing Streamlit UI and the REST API
# the React frontend calls. Streamlit itself is run exactly as before, just on
# an internal port behind nginx.
set -euo pipefail

# Public port: Railway injects $PORT; HF Spaces uses the Dockerfile app_port.
export NGINX_PORT="${PORT:-8501}"

# Render the nginx config with the chosen port.
envsubst '${NGINX_PORT}' < /app/deploy/nginx.conf.template > /etc/nginx/conf.d/default.conf

# FastAPI (internal) — the API surface for the React app.
uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1 &

# Streamlit (internal) — the original app, unchanged.
streamlit run streamlit_app.py \
    --server.address=127.0.0.1 \
    --server.port=8503 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false &

# If any background service dies, take the container down so the platform
# restarts it (restartPolicy handles the rest).
term() { kill -TERM "$nginx_pid" 2>/dev/null || true; }
trap term SIGINT SIGTERM

# nginx in the foreground on the public port.
nginx -g 'daemon off;' &
nginx_pid=$!
wait -n
exit $?
