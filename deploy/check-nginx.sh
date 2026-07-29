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
# That reasoning only holds if the validator TRACKS the Dockerfile. Two things
# enforce it: the base image is read out of the Dockerfile rather than
# duplicated here, and the image tag is a hash of the recipe — change the base
# or the package list and the tag changes, so a stale image cannot be reused.
#
# Rendering runs inside the container with envsubst, exactly as deploy/start.sh
# does it. Rendering differently here would validate a file production never
# builds — the same false safety net in another disguise.
#
# Usage:  bash deploy/check-nginx.sh
#         NGINX_PORT=8080 bash deploy/check-nginx.sh
# Requires Docker. Exits non-zero when the config is invalid.
set -euo pipefail

cd "$(dirname "$0")/.."

TEMPLATE="deploy/nginx.conf.template"
[ -f "$TEMPLATE" ] || { echo "Missing ${TEMPLATE}" >&2; exit 2; }

# The port reaches nginx through envsubst, so a hostile value cannot break out
# of the template — but a typo'd port fails deep inside `nginx -t` with an
# opaque message. Reject it here, where the error can name the cause.
NGINX_PORT="${NGINX_PORT:-8501}"
if ! [[ "$NGINX_PORT" =~ ^[0-9]+$ ]] || [ "$NGINX_PORT" -lt 1 ] || [ "$NGINX_PORT" -gt 65535 ]; then
    echo "NGINX_PORT must be a number in 1-65535 (got: '${NGINX_PORT}')" >&2
    exit 2
fi

# Track the Dockerfile's base rather than hardcoding it a second time.
BASE_IMAGE="$(awk '/^FROM /{print $2; exit}' Dockerfile)"
[ -n "$BASE_IMAGE" ] || { echo "Could not read a FROM line from Dockerfile" >&2; exit 2; }

# Mirrors the Dockerfile: same base, same nginx + gettext-base packages, and the
# same removal of Debian's default site (which otherwise occupies port 80 and is
# not what production serves).
RECIPE="FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends nginx gettext-base \\
    && rm -rf /var/lib/apt/lists/* \\
    && rm -f /etc/nginx/sites-enabled/default"

# Tagging by recipe hash is what makes reuse safe: a different base or package
# set is a different tag, so `docker image inspect` misses and rebuilds.
RECIPE_HASH="$(printf '%s' "$RECIPE" | sha1sum | cut -c1-12)"
VALIDATOR_IMAGE="researchrag-nginx-validator:${RECIPE_HASH}"

if ! docker image inspect "$VALIDATOR_IMAGE" >/dev/null 2>&1; then
    echo "Building validator image for ${BASE_IMAGE} (${RECIPE_HASH})…"
    printf '%s\n' "$RECIPE" | docker build -t "$VALIDATOR_IMAGE" -f - . >/dev/null
fi

# Docker Desktop needs a Windows-style path; `pwd -W` provides it under Git Bash
# and is simply absent elsewhere, where the POSIX path already works.
HOST_DIR="$(pwd -W 2>/dev/null || pwd)"

echo "Validating ${TEMPLATE} (NGINX_PORT=${NGINX_PORT})…"

# envsubst with an explicit variable list, matching deploy/start.sh, so nginx
# sees precisely the file the container will serve.
if MSYS_NO_PATHCONV=1 docker run --rm \
        -e "NGINX_PORT=${NGINX_PORT}" \
        -v "${HOST_DIR}/${TEMPLATE}:/tmp/nginx.conf.template:ro" \
        "$VALIDATOR_IMAGE" \
        sh -c 'envsubst "\${NGINX_PORT}" < /tmp/nginx.conf.template \
                 > /etc/nginx/conf.d/default.conf && nginx -t' 2>&1 | sed 's/^/  /'; then
    echo "OK — nginx accepts the rendered config."
else
    echo "FAILED — fix ${TEMPLATE} before deploying." >&2
    exit 1
fi
