#!/usr/bin/env bash
# 从 dev-backup.sh 生成的备份目录恢复数据
#
# 用法：
#   bash scripts/dev-restore.sh .backups/20260705_143000
#
# 前提：Postgres / Neo4j 容器已通过 dev-up.sh / dev-prepare.sh 启动
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${1:-}"

if [[ -z "$BACKUP_DIR" ]]; then
  echo "用法: bash scripts/dev-restore.sh <备份目录>"
  echo ""
  echo "可用备份："
  ls -1 "$ROOT/.backups" 2>/dev/null | sed 's/^/  /' || echo "  (无备份，请先运行 dev-backup.sh)"
  exit 1
fi

# 支持传相对路径或仅传时间戳
if [[ ! -d "$BACKUP_DIR" ]]; then
  if [[ -d "$ROOT/.backups/$BACKUP_DIR" ]]; then
    BACKUP_DIR="$ROOT/.backups/$BACKUP_DIR"
  else
    echo "✗ 备份目录不存在: $BACKUP_DIR"
    exit 1
  fi
fi

echo "============================================"
echo "  从备份恢复: $BACKUP_DIR"
echo "============================================"

if ! docker inspect finnews_postgres >/dev/null 2>&1; then
  echo "✗ finnews_postgres 未运行，请先: bash scripts/dev-up.sh"
  exit 1
fi

# ── Postgres ──
if [[ -f "$BACKUP_DIR/postgres.sql" ]]; then
  echo ""
  echo "[1/2] 恢复 Postgres..."
  read -p "  ⚠ 将覆盖当前 finnews_db 数据，确认？(y/N): " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker exec -i finnews_postgres psql -U finnews -d finnews_db < "$BACKUP_DIR/postgres.sql"
    echo "  ✓ Postgres 恢复完成"
  else
    echo "  - 已取消 Postgres 恢复"
  fi
else
  echo ""
  echo "[1/2] 未找到 postgres.sql，跳过"
fi

# ── Neo4j ──
if [[ -f "$BACKUP_DIR/neo4j_export.cypher" ]]; then
  echo ""
  echo "[2/2] 恢复 Neo4j 知识图谱..."
  if ! docker inspect finnews_neo4j >/dev/null 2>&1; then
    echo "  ✗ finnews_neo4j 未运行，跳过"
  else
    docker cp "$BACKUP_DIR/neo4j_export.cypher" finnews_neo4j:/var/lib/neo4j/import/restore.cypher
    docker exec finnews_neo4j cypher-shell -u neo4j -p finnews_neo4j_password \
      -f /var/lib/neo4j/import/restore.cypher
    echo "  ✓ Neo4j 恢复完成"
  fi
else
  echo ""
  echo "[2/2] 未找到 neo4j_export.cypher，跳过"
fi

# ── Milvus（可选） ──
if [[ -f "$BACKUP_DIR/milvus_data.tar.gz" ]]; then
  echo ""
  echo "检测到 Milvus 备份 (milvus_data.tar.gz)。"
  read -p "  是否恢复？会覆盖当前向量数据，需先 dev-down.sh --all 停止容器 (y/N): " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker run --rm \
      -v deploy_milvus_data:/data \
      -v "$BACKUP_DIR":/backup \
      alpine sh -c "rm -rf /data/* && tar xzf /backup/milvus_data.tar.gz -C /data"
    echo "  ✓ Milvus 数据恢复完成，请重新 dev-up.sh"
  fi
fi

echo ""
echo "============================================"
echo "  恢复流程结束"
echo "============================================"
