#!/usr/bin/env bash
# Validate deploy/nginx.conf.template against a real nginx BEFORE deploying.
#
# Why this exists: conf.d/*.conf is included inside the distro's http{} block,
# so a directive already set in /etc/nginx/nginx.conf becomes a fatal
# "duplicate directive" and the container refuses to start. That cost two failed
# Space deploys.
#
# Why it does NOT use the official `nginx` image: that image ships its own
# nginx.conf with `#gzip on;` commented out, while the Debian *package* our
# Dockerfile installs has `gzip on;` active. Validating against the wrong base
# silently PASSES the exact config that breaks production — a false safety net.
# So we build a throwaway image from the same base + package as the Dockerfile.
#
# Usage:  bash deploy/check-nginx.sh
# Requires Docker. Exits non-zero when the config is invalid.
set -euo pipefail

cd "$(dirname "$0")/.."

VALIDATOR_IMAGE="researchrag-nginx-validator:latest"

# Build once, reuse thereafter (a few seconds when cached).
if ! docker image inspect "$VALIDATOR_IMAGE" >/dev/null 2>&1; then
    echo "Building validator image (mirrors Dockerfile's nginx install)…"
    docker build -t "$VALIDATOR_IMAGE" -f - . >/dev/null <<'DOCKERFILE'
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends nginx gettext-base \
    && rm -rf /var/lib/apt/lists/*
DOCKERFILE
fi

# Render next to the repo rather than /tmp: on Git Bash / Docker Desktop a
# /tmp path is an MSYS path the daemon cannot bind-mount.
RENDERED_NAME=".nginx-check.conf"
RENDERED="$(pwd)/${RENDERED_NAME}"
trap 'rm -f "$RENDERED"' EXIT

NGINX_PORT="${NGINX_PORT:-8501}"
sed "s|\${NGINX_PORT}|${NGINX_PORT}|g" deploy/nginx.conf.template > "$RENDERED"

# Docker Desktop needs a Windows-style path; `pwd -W` provides it under Git Bash
# and is simply absent elsewhere, where the POSIX path already works.
HOST_DIR="$(pwd -W 2>/dev/null || pwd)"

echo "Validating deploy/nginx.conf.template (NGINX_PORT=${NGINX_PORT})…"

if MSYS_NO_PATHCONV=1 docker run --rm \
        -v "${HOST_DIR}/${RENDERED_NAME}:/etc/nginx/conf.d/default.conf:ro" \
        "$VALIDATOR_IMAGE" nginx -t 2>&1 | sed 's/^/  /'; then
    echo "OK — nginx accepts the rendered config."
else
    echo "FAILED — fix deploy/nginx.conf.template before deploying." >&2
    exit 1
fi
