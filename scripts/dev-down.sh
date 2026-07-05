#!/usr/bin/env bash
# 停止 FinnewsHunter 开发栈
#   默认：仅停止本地 API + 前端（Docker 中间件保持运行，下次 dev-up 更快）
#   --all：同时停止 Docker 容器
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.runtime/dev"
COMPOSE="$ROOT/deploy/docker-compose.dev.yml"

WITH_DOCKER=false
PURGE=false
case "${1:-}" in
  --all) WITH_DOCKER=true ;;
  --purge) WITH_DOCKER=true; PURGE=true ;;
esac

stop_one() {
  local name="$1"
  local pid_file="$RUNTIME/$name.pid"

  if [[ ! -f "$pid_file" ]]; then
    echo "  - $name 未运行"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    echo "  ✓ 已停止 $name (pid $pid)"
  else
    echo "  - $name 进程已不存在 (pid $pid)"
  fi
  rm -f "$pid_file"
}

echo "停止 FinnewsHunter 开发进程..."
stop_one api
stop_one frontend

# 兼容旧版 dev-up 可能遗留的本地 Celery 进程
stop_one celery-worker
stop_one celery-beat

if [[ "$WITH_DOCKER" == true ]]; then
  if [[ "$PURGE" == true ]]; then
    echo ""
    echo "⚠⚠⚠ --purge 会删除 Postgres/Neo4j/Milvus 全部数据卷，不可恢复 ⚠⚠⚠"
    echo "建议先备份: bash scripts/dev-backup.sh"
    read -p "确认要删除所有数据卷？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "已取消。"
      exit 0
    fi
    docker compose -f "$COMPOSE" down -v
    echo "  ✓ Docker 容器与数据卷已全部删除"
  else
    echo ""
    echo "停止 Docker 容器（保留数据卷，数据不会丢失）..."
    docker compose -f "$COMPOSE" down
    echo "  ✓ Docker 已全部停止（数据卷仍保留，下次 dev-up.sh 数据还在）"
    echo "  如需连数据卷也删除（不可恢复）: bash scripts/dev-down.sh --purge"
  fi
else
  echo ""
  echo "Docker 中间件仍在运行（保留数据，下次 dev-up 更快）。"
  echo "若要一并停止 Docker：bash scripts/dev-down.sh --all"
fi

echo "完成。"
