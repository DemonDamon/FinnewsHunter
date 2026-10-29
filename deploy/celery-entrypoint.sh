#!/usr/bin/env bash
# Author: Damon Li
# Preserve the legacy development fallback while keeping research images immutable at runtime.

set -euo pipefail

if [ "${APP_MODE:-legacy}" = "research" ]; then
    python -m pip check
    exec "$@"
fi

# The legacy volume-mounted development path retains its existing dependency fallback.
CHECK_PACKAGES=("celery" "fastapi" "sqlalchemy")
NEED_INSTALL=false

for package in "${CHECK_PACKAGES[@]}"; do
    if ! python -c "import ${package}" >/dev/null 2>&1; then
        NEED_INSTALL=true
        break
    fi
done

if [ "$NEED_INSTALL" = true ]; then
    printf '%s\n' "Legacy dependency fallback is installing requirements."
    python -m pip install --no-cache-dir -r /app/requirements.txt
fi

exec "$@"
