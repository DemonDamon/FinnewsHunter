#!/usr/bin/env bash
# FinnewsHunter 开发环境一次性准备（依赖、配置、数据库初始化）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

echo "============================================"
echo "  FinnewsHunter dev-prepare（首次 / 换机）"
echo "============================================"

# 1. Docker
echo ""
echo "[1/5] 检查 Docker..."
if ! docker info >/dev/null 2>&1; then
  echo "  ✗ Docker 未运行，请先启动 Docker Desktop"
  exit 1
fi
echo "  ✓ Docker 可用"

# 2. Python 环境
echo ""
echo "[2/5] 后端 Python 依赖..."
if [[ -x /opt/miniconda3/bin/python ]]; then
  PYTHON=/opt/miniconda3/bin/python
  PIP=/opt/miniconda3/bin/pip
else
  PYTHON="$(command -v python3 || command -v python)"
  PIP="$(command -v pip3 || command -v pip)"
fi
cd "$BACKEND"
if [[ ! -f .env ]]; then
  echo "  → 未找到 .env，从 env.example 复制..."
  cp env.example .env
  echo "  ⚠ 请编辑 backend/.env 填入 LLM API Key（如 DASHSCOPE_API_KEY）"
else
  echo "  ✓ .env 已存在"
fi
"$PIP" install -r requirements.txt -q
echo "  ✓ pip 依赖已安装"

# 3. 前端依赖
echo ""
echo "[3/5] 前端 npm 依赖..."
cd "$FRONTEND"
if [[ ! -d node_modules ]]; then
  npm install
else
  echo "  ✓ node_modules 已存在（跳过 npm install）"
fi

# 4. 拉起中间件并等待就绪（为 init_db 做准备）
echo ""
echo "[4/5] 启动 Docker 中间件并等待就绪..."
docker compose -f "$ROOT/deploy/docker-compose.dev.yml" up -d \
  postgres redis milvus-etcd milvus-minio milvus-standalone neo4j

echo "  → 等待 Postgres / Redis 健康检查..."
for i in {1..30}; do
  pg_ok=$(docker inspect --format='{{.State.Health.Status}}' finnews_postgres 2>/dev/null || echo "starting")
  redis_ok=$(docker inspect --format='{{.State.Health.Status}}' finnews_redis 2>/dev/null || echo "starting")
  if [[ "$pg_ok" == "healthy" && "$redis_ok" == "healthy" ]]; then
    break
  fi
  sleep 2
done

# 5. 初始化数据库
echo ""
echo "[5/5] 初始化数据库..."
cd "$BACKEND"
"$PYTHON" init_db.py || echo "  （数据库可能已初始化，跳过）"

echo ""
echo "============================================"
echo "  准备完成"
echo "============================================"
echo "  下一步：bash scripts/dev-up.sh"
echo ""
echo "  访问地址（启动后）："
echo "    前端  http://localhost:3000"
echo "    API   http://localhost:8000/docs"
echo "============================================"
