#!/bin/bash

# ---------------------------------------------------------------------------
# SSH — Azure App Service uses port 2222 for the in-portal SSH console.
# Failure is non-fatal: the app must still start even if sshd cannot bind.
# ---------------------------------------------------------------------------
mkdir -p /var/run/sshd
/usr/sbin/sshd || echo "[start.sh] WARNING: sshd failed to start (non-fatal)"

# ---------------------------------------------------------------------------
# Validate required secrets are present before attempting to launch gunicorn.
# Missing any of these makes the Python app crash at import time.
# ---------------------------------------------------------------------------
missing=""
for var in ADMIN_USERNAME ADMIN_PASSWORD JWT_SECRET_KEY; do
    eval val="\$$var"
    if [ -z "$val" ]; then
        missing="$missing $var"
    fi
done
if [ -n "$missing" ]; then
    echo "[start.sh] ERROR: Required environment variables not set:$missing"
    echo "[start.sh] Set them in Azure App Service -> Configuration -> Application settings."
    exit 1
fi

# ---------------------------------------------------------------------------
# Dynamic worker count: 2 * CPU + 1 unless WEB_CONCURRENCY is already set.
# ---------------------------------------------------------------------------
if [ -z "${WEB_CONCURRENCY}" ]; then
    CPU_COUNT="$(nproc --all 2>/dev/null || echo 1)"
    WEB_CONCURRENCY="$((CPU_COUNT * 2 + 1))"
    export WEB_CONCURRENCY
fi

if [ "${1:-}" = "gunicorn" ] && ! printf ' %s ' "$*" | grep -q ' --workers '; then
    set -- "$@" "--workers" "${WEB_CONCURRENCY}"
fi

exec "$@"
