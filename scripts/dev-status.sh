#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/dev"
LOG_DIR="$ROOT/.runtime/logs"

check_local() {
  local name="$1"
  local port="${2:-}"
  local pid_file="$RUNTIME/$name.pid"

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "  ✓ $name  running  pid=$(cat "$pid_file")"
  else
    echo "  ✗ $name  stopped"
  fi

  if [[ -n "$port" ]]; then
    if lsof -i ":$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "      port $port listening"
    else
      echo "      port $port not listening"
    fi
  fi
}

check_docker() {
  local name="$1"
  local status
  status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
  if [[ "$status" == "running" ]]; then
    local health
    health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$name" 2>/dev/null)
    echo "  ✓ $name  running  ($health)"
  elif [[ "$status" == "missing" ]]; then
    echo "  ✗ $name  not found"
  else
    echo "  ✗ $name  $status"
  fi
}

echo "============================================"
echo "  FinnewsHunter 开发环境状态"
echo "============================================"
echo ""
echo "本地进程："
check_local api 8000
check_local frontend 3000
echo ""
echo "Docker 中间件："
check_docker finnews_postgres
check_docker finnews_redis
check_docker finnews_neo4j
check_docker finnews_milvus
echo ""
echo "Docker 任务队列（定向爬取依赖此项）："
check_docker finnews_celery_worker
check_docker finnews_celery_beat
echo ""
echo "日志: $LOG_DIR"
echo "============================================"
