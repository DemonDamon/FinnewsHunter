#!/usr/bin/env bash
# 备份 FinnewsHunter 持久化数据（Postgres + Neo4j，可选 Milvus）
#
# 用法：
#   bash scripts/dev-backup.sh              # 备份 Postgres + Neo4j
#   bash scripts/dev-backup.sh --with-milvus # 额外备份 Milvus 向量数据（体积较大）
#
# 备份产物在 FinnewsHunter/.backups/<timestamp>/，不纳入 git（见 .gitignore）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$ROOT/.backups/$TS"
WITH_MILVUS=false

if [[ "${1:-}" == "--with-milvus" ]]; then
  WITH_MILVUS=true
fi

mkdir -p "$BACKUP_DIR"

echo "============================================"
echo "  FinnewsHunter 数据备份 → $BACKUP_DIR"
echo "============================================"

# ── Postgres ──
echo ""
echo "[1/3] 备份 Postgres (news / crawl_tasks / analyses 等)..."
if docker inspect finnews_postgres >/dev/null 2>&1; then
  docker exec finnews_postgres pg_dump -U finnews -d finnews_db \
    --clean --if-exists > "$BACKUP_DIR/postgres.sql"
  echo "  ✓ postgres.sql ($(du -h "$BACKUP_DIR/postgres.sql" | cut -f1))"
else
  echo "  ✗ finnews_postgres 容器不存在，跳过（先 dev-up.sh 启动服务）"
fi

# ── Neo4j（知识图谱） ──
echo ""
echo "[2/3] 备份 Neo4j 知识图谱..."
if docker inspect finnews_neo4j >/dev/null 2>&1; then
  docker exec finnews_neo4j cypher-shell -u neo4j -p finnews_neo4j_password \
    "CALL apoc.export.cypher.all('/var/lib/neo4j/import/neo4j_export.cypher', {format: 'cypher-shell'})" \
    >/dev/null 2>&1 || echo "  ⚠ apoc.export 失败（可能无写入数据），跳过"
  if docker exec finnews_neo4j test -f /var/lib/neo4j/import/neo4j_export.cypher 2>/dev/null; then
    docker cp finnews_neo4j:/var/lib/neo4j/import/neo4j_export.cypher "$BACKUP_DIR/neo4j_export.cypher"
    echo "  ✓ neo4j_export.cypher ($(du -h "$BACKUP_DIR/neo4j_export.cypher" | cut -f1))"
  fi
else
  echo "  ✗ finnews_neo4j 容器不存在，跳过"
fi

# ── Milvus（向量库，可选） ──
echo ""
echo "[3/3] Milvus 向量数据..."
if [[ "$WITH_MILVUS" == true ]]; then
  if docker volume inspect deploy_milvus_data >/dev/null 2>&1; then
    docker run --rm \
      -v deploy_milvus_data:/data:ro \
      -v "$BACKUP_DIR":/backup \
      alpine tar czf /backup/milvus_data.tar.gz -C /data .
    echo "  ✓ milvus_data.tar.gz ($(du -h "$BACKUP_DIR/milvus_data.tar.gz" | cut -f1))"
  else
    echo "  ✗ deploy_milvus_data volume 不存在，跳过"
  fi
else
  echo "  - 跳过（向量可从 Postgres 新闻数据重新生成；如需备份加 --with-milvus）"
fi

echo ""
echo "============================================"
echo "  备份完成: $BACKUP_DIR"
echo "  恢复命令: bash scripts/dev-restore.sh $BACKUP_DIR"
echo "============================================"
