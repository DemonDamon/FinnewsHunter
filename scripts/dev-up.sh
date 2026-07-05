#!/usr/bin/env bash
# 一键启动 FinnewsHunter 完整开发栈
#   Docker：中间件 + Celery Worker/Beat
#   本地：FastAPI + Vite 前端（热重载）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
COMPOSE="$ROOT/deploy/docker-compose.dev.yml"
RUNTIME="$ROOT/.runtime/dev"
LOG_DIR="$ROOT/.runtime/logs"

mkdir -p "$RUNTIME" "$LOG_DIR"

if [[ -x /opt/miniconda3/bin/python ]]; then
  UVICORN=/opt/miniconda3/bin/uvicorn
else
  UVICORN="$(command -v uvicorn)"
fi

# akshare / 爬虫需直连国内站点
for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY; do
  unset "$var" || true
done

start_bg() {
  local name="$1"
  local pid_file="$RUNTIME/$name.pid"
  local log_file="$LOG_DIR/$name.log"
  shift

  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "  ✓ $name 已在运行 (pid $(cat "$pid_file"))"
    return 0
  fi

  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "  ✓ $name 已启动 (pid $(cat "$pid_file"), log: $log_file)"
}

echo "============================================"
echo "  FinnewsHunter dev-up"
echo "============================================"

# ── 检查前置条件 ──
if [[ ! -f "$BACKEND/.env" ]]; then
  echo "  ✗ 未找到 backend/.env，请先运行: bash scripts/dev-prepare.sh"
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "  ✗ Docker 未运行，请先启动 Docker Desktop"
  exit 1
fi

# ── [1/3] Docker：中间件 + Celery ──
echo ""
echo "[1/3] Docker 全栈（中间件 + Celery Worker/Beat）..."
docker compose -f "$COMPOSE" up -d \
  postgres redis \
  milvus-etcd milvus-minio milvus-standalone \
  neo4j \
  celery-worker celery-beat

echo "  → 等待核心服务就绪..."
for i in {1..30}; do
  pg_ok=$(docker inspect --format='{{.State.Health.Status}}' finnews_postgres 2>/dev/null || echo "starting")
  redis_ok=$(docker inspect --format='{{.State.Health.Status}}' finnews_redis 2>/dev/null || echo "starting")
  if [[ "$pg_ok" == "healthy" && "$redis_ok" == "healthy" ]]; then
    break
  fi
  sleep 2
done

celery_status=$(docker inspect --format='{{.State.Status}}' finnews_celery_worker 2>/dev/null || echo "missing")
if [[ "$celery_status" != "running" ]]; then
  echo "  ⚠ Celery Worker 未运行，查看日志: docker logs finnews_celery_worker"
else
  echo "  ✓ Celery Worker 运行中"
fi

# ── [2/3] 本地 FastAPI ──
echo ""
echo "[2/3] 后端 API (8000)..."
cd "$BACKEND"
start_bg api "$UVICORN" app.main:app --reload --host 0.0.0.0 --port 8000

# ── [3/3] 本地 Vite 前端 ──
echo ""
echo "[3/3] 前端 (3000)..."
cd "$FRONTEND"
if [[ ! -d node_modules ]]; then
  echo "  → 首次运行，安装前端依赖..."
  npm install
fi
start_bg frontend npm run dev

echo ""
echo "============================================"
echo "  全部已启动"
echo "============================================"
echo ""
echo "  架构："
echo "    Docker  → Postgres / Redis / Milvus / Neo4j / Celery"
echo "    本地    → FastAPI :8000 / Vite :3000"
echo ""
echo "  访问："
echo "    前端  http://localhost:3000"
echo "    API   http://localhost:8000/docs"
echo "    Neo4j http://localhost:7474"
echo ""
echo "  管理："
echo "    状态  bash scripts/dev-status.sh"
echo "    停止  bash scripts/dev-down.sh"
echo "    日志  tail -f $LOG_DIR/*.log"
echo "    Celery docker logs -f finnews_celery_worker"
echo "============================================"
