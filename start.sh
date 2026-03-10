#!/bin/bash
set -e

# SSHD requires this runtime directory.
mkdir -p /var/run/sshd
/usr/sbin/sshd

# Default to a CPU-based worker count unless explicitly provided.
if [ -z "${WEB_CONCURRENCY}" ]; then
	CPU_COUNT="$(nproc --all 2>/dev/null || echo 1)"
	WEB_CONCURRENCY="$((CPU_COUNT * 2 + 1))"
	export WEB_CONCURRENCY
fi

# If Gunicorn is started without an explicit workers flag, inject the dynamic value.
if [ "${1:-}" = "gunicorn" ] && ! printf ' %s ' "$*" | grep -q ' --workers '; then
	set -- "$@" "--workers" "${WEB_CONCURRENCY}"
fi

exec "$@"