#!/usr/bin/env bash
# Author: Damon Li
# Start the existing FinnewsHunter application in legacy or isolated research mode.

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
DEPLOY_DIR="$PROJECT_DIR/deploy"
DEV_COMPOSE_FILE="$DEPLOY_DIR/docker-compose.dev.yml"
RESEARCH_COMPOSE_FILE="$DEPLOY_DIR/docker-compose.research.yml"
PYTHON_BIN="${PYTHON_BIN:-python}"
UVICORN_BIN="${UVICORN_BIN:-uvicorn}"

MODE="legacy"
CHECK_ONLY=false
NO_SERVICES=false
WITH_WORKER=false
RESEARCH_ENABLED_VALUE="${RESEARCH_ENABLED:-false}"
RESEARCH_EXECUTION_ENABLED_VALUE="${RESEARCH_EXECUTION_ENABLED:-false}"
COMPOSE_COMMAND=()
COMPOSE_FILES=()
COMPOSE_SUPPORTS_WAIT=false

usage() {
    cat <<'EOF'
Usage: start.sh [--mode legacy|research] [--check] [--no-services] [--with-worker]

Modes:
  legacy                 Start the existing full legacy service set (default).
  research               Start only the isolated research dependencies by default.

Options:
  --check                Validate the selected Compose configuration only.
  --no-services          Research-only app diagnostic without Compose services.
  --with-worker          Start the optional research worker when modules are registered.
  -h, --help             Show this help message.
EOF
}

fatal() {
    printf '%s\n' "$1" >&2
    exit "${2:-1}"
}

is_enabled() {
    local normalized
    normalized="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    case "$normalized" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

parse_arguments() {
    while (($# > 0)); do
        case "$1" in
            --mode)
                (($# >= 2)) || fatal "--mode requires legacy or research"
                MODE="$2"
                shift 2
                ;;
            --mode=*)
                MODE="${1#*=}"
                shift
                ;;
            --check)
                CHECK_ONLY=true
                shift
                ;;
            --no-services)
                NO_SERVICES=true
                shift
                ;;
            --with-worker)
                WITH_WORKER=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                fatal "Unknown option: $1"
                ;;
        esac
    done

    case "$MODE" in
        legacy|research) ;;
        *) fatal "Unsupported mode: $MODE" ;;
    esac

    if [[ "$NO_SERVICES" == true && "$MODE" != "research" ]]; then
        fatal "--no-services is only available in research mode"
    fi
    if [[ "$WITH_WORKER" == true && "$MODE" != "research" ]]; then
        fatal "--with-worker is only available in research mode"
    fi
    if [[ "$WITH_WORKER" == true && "$NO_SERVICES" == true ]]; then
        fatal "--with-worker cannot be combined with --no-services"
    fi
    if [[ "$WITH_WORKER" == true && "$CHECK_ONLY" == true ]]; then
        fatal "--with-worker cannot be combined with --check"
    fi
}

select_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_COMMAND=(docker compose)
        COMPOSE_SUPPORTS_WAIT=true
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_COMMAND=(docker-compose)
    else
        fatal "Docker Compose is required (docker compose or docker-compose)"
    fi

    COMPOSE_FILES=(-f "$DEV_COMPOSE_FILE")
    if [[ "$MODE" == "research" ]]; then
        [[ -f "$RESEARCH_COMPOSE_FILE" ]] || fatal "Research Compose override is missing: $RESEARCH_COMPOSE_FILE"
        COMPOSE_FILES+=(-f "$RESEARCH_COMPOSE_FILE")
    fi
}

compose() {
    "${COMPOSE_COMMAND[@]}" "${COMPOSE_FILES[@]}" "$@"
}

compose_check() {
    if [[ "$COMPOSE_SUPPORTS_WAIT" == true ]]; then
        compose config --format json >/dev/null
    else
        compose config >/dev/null
    fi
}

wait_for_legacy_compose() {
    local attempts=0
    local max_attempts=30

    while ((attempts < max_attempts)); do
        if compose exec -T postgres pg_isready -U finnews -d finnews_db >/dev/null 2>&1 \
            && compose exec -T redis redis-cli ping >/dev/null 2>&1; then
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 2
    done

    fatal "Timed out waiting for PostgreSQL and Redis health checks"
}

start_compose_services() {
    if [[ "$COMPOSE_SUPPORTS_WAIT" == true ]]; then
        if (($# > 0)); then
            compose up -d --wait "$@"
        else
            compose up -d --wait
        fi
    else
        if (($# > 0)); then
            compose up -d "$@"
        else
            compose up -d
        fi
        wait_for_legacy_compose
    fi
}

registered_research_worker_modules() {
    (
        cd "$SCRIPT_DIR"
        APP_MODE=research \
            RESEARCH_ENABLED="$RESEARCH_ENABLED_VALUE" \
            RESEARCH_EXECUTION_ENABLED="$RESEARCH_EXECUTION_ENABLED_VALUE" \
            PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
            "$PYTHON_BIN" -c '
from app.core.config import Settings
from app.research.composition import build_research_components

components = build_research_components(Settings())
print(" ".join(components.worker_modules))
'
    )
}

verify_research_worker_modules() {
    local modules
    if ! modules="$(registered_research_worker_modules)"; then
        fatal "Research worker is unavailable: component registry could not be loaded"
    fi
    if [[ -z "${modules//[[:space:]]/}" ]]; then
        fatal "Research worker is unavailable: no worker modules are registered"
    fi
}

verify_research_migrations() {
    if ! is_enabled "$RESEARCH_ENABLED_VALUE"; then
        return 0
    fi

    if [[ ! -f "$SCRIPT_DIR/alembic.ini" || ! -d "$SCRIPT_DIR/alembic" ]]; then
        fatal "Alembic migration files are required when RESEARCH_ENABLED=true"
    fi
}

run_research_migrations() {
    if ! is_enabled "$RESEARCH_ENABLED_VALUE"; then
        return 0
    fi

    (
        cd "$SCRIPT_DIR"
        APP_MODE=research \
            RESEARCH_ENABLED="$RESEARCH_ENABLED_VALUE" \
            RESEARCH_EXECUTION_ENABLED="$RESEARCH_EXECUTION_ENABLED_VALUE" \
            "$PYTHON_BIN" -m alembic -c "$SCRIPT_DIR/alembic.ini" upgrade head
    )
}

start_application() {
    cd "$SCRIPT_DIR"
    exec env \
        APP_MODE="$MODE" \
        RESEARCH_ENABLED="$RESEARCH_ENABLED_VALUE" \
        RESEARCH_EXECUTION_ENABLED="$RESEARCH_EXECUTION_ENABLED_VALUE" \
        PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        "$UVICORN_BIN" app.main:app --reload --host 0.0.0.0 --port 8000
}

start_legacy() {
    select_compose
    printf '%s\n' "Starting legacy Compose services..."
    start_compose_services

    printf '%s\n' "Running legacy database initializer..."
    (
        cd "$SCRIPT_DIR"
        APP_MODE=legacy "$PYTHON_BIN" init_db.py
    ) || printf '%s\n' "Database initialization skipped (may already exist)"

    start_application
}

start_research() {
    if [[ "$NO_SERVICES" == true ]]; then
        if is_enabled "$RESEARCH_ENABLED_VALUE"; then
            fatal "--no-services is a pure diagnostic and requires RESEARCH_ENABLED=false"
        fi
        printf '%s\n' "Starting research application without Compose services..."
        start_application
    fi

    verify_research_migrations
    if [[ "$WITH_WORKER" == true ]]; then
        verify_research_worker_modules
    fi

    select_compose
    printf '%s\n' "Starting isolated research Compose services..."
    local services=(postgres redis)
    if [[ "$WITH_WORKER" == true ]]; then
        services+=(celery-worker)
    fi
    start_compose_services "${services[@]}"

    run_research_migrations
    start_application
}

parse_arguments "$@"

if [[ "$CHECK_ONLY" == true ]]; then
    select_compose
    compose_check
    printf '%s\n' "Compose configuration is valid for mode: $MODE"
    exit 0
fi

if [[ "$MODE" == "research" && "$NO_SERVICES" == true ]]; then
    start_research
fi

if [[ "$MODE" == "legacy" ]]; then
    start_legacy
else
    start_research
fi
