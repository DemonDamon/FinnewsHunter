#!/bin/bash
# Celery 容器化重启脚本
# 用法: ./start_celery.sh [--restart|-r] [--force-recreate|-f] [--rebuild|-b] [--logs|-l]

set -e

# 解析命令行参数
AUTO_RESTART=false
FORCE_RECREATE=false
REBUILD_IMAGE=false
SHOW_LOGS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --restart|-r)
            AUTO_RESTART=true
            shift
            ;;
        --force-recreate|-f)
            FORCE_RECREATE=true
            AUTO_RESTART=true
            shift
            ;;
        --rebuild|-b)
            REBUILD_IMAGE=true
            FORCE_RECREATE=true
            AUTO_RESTART=true
            shift
            ;;
        --logs|-l)
            SHOW_LOGS=true
            shift
            ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --restart, -r        自动重启容器（容器使用 python:3.11 基础镜像 + volumes 挂载）"
            echo "  --force-recreate, -f 强制重建容器（会重新安装依赖，因为使用基础镜像）"
            echo "  --rebuild, -b        重新构建镜像（构建的镜像不会被使用，仅用于清理未使用的镜像）"
            echo "  --logs, -l           重启后自动显示日志"
            echo "  --help, -h           显示帮助信息"
            echo ""
            echo "注意:"
            echo "  - 当前容器使用 python:3.11 基础镜像 + volumes 挂载代码"
            echo "  - 每次启动容器都会执行 pip install 安装依赖"
            echo "  - --rebuild 选项会构建镜像，但构建的镜像不会被容器使用"
            echo ""
            echo "示例:"
            echo "  $0                   交互式重启容器"
            echo "  $0 --restart         自动重启容器"
            echo "  $0 -r -l             自动重启并显示日志"
            echo "  $0 -f                强制重建容器（会重新安装依赖）"
            echo "  $0 --rebuild         重新构建镜像（仅用于清理未使用的镜像）"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

echo "============================================"
echo "  FinnewsHunter Celery 容器重启脚本"
echo "============================================"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "Docker 未运行，请先启动 Docker"
    exit 1
fi

# 检查 docker-compose 文件是否存在
COMPOSE_FILE="../deploy/docker-compose.dev.yml"
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "找不到 docker-compose 文件: $COMPOSE_FILE"
    exit 1
fi

# 检查容器状态
echo ""
echo "[1/4] 检查 Celery 容器状态..."
WORKER_RUNNING=$(docker ps -q -f name=finnews_celery_worker)
BEAT_RUNNING=$(docker ps -q -f name=finnews_celery_beat)

if [ -n "$WORKER_RUNNING" ] || [ -n "$BEAT_RUNNING" ]; then
    echo "检测到 Celery 容器正在运行"
    echo "   - Worker: $([ -n "$WORKER_RUNNING" ] && echo "运行中 ($WORKER_RUNNING)" || echo "未运行")"
    echo "   - Beat: $([ -n "$BEAT_RUNNING" ] && echo "运行中 ($BEAT_RUNNING)" || echo "未运行")"
    
    if [ "$AUTO_RESTART" = false ]; then
        read -p "是否重启容器？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "已取消重启"
            exit 0
        fi
    else
        echo "自动重启模式，无需确认"
    fi
fi

# 检查 Redis 是否运行
echo ""
echo "[2/4] 检查 Redis 连接..."
if docker exec finnews_redis redis-cli ping > /dev/null 2>&1; then
    echo "Redis 正常运行"
else
    echo "Redis 未运行，请先启动 Docker Compose:"
    echo "   cd ../deploy && docker-compose -f docker-compose.dev.yml up -d redis"
    exit 1
fi

# 重启 Celery Worker 容器
echo ""
cd ../deploy

if [ "$REBUILD_IMAGE" = true ]; then
    echo "[3/5] 重新构建镜像（注意：构建的镜像不会被容器使用，仅用于清理未使用的镜像）..."
    docker-compose -f docker-compose.dev.yml build celery-worker celery-beat
    echo "[4/5] 强制重建 Celery Worker 容器（使用 python:3.11 基础镜像 + volumes 挂载）..."
    docker-compose -f docker-compose.dev.yml up -d --force-recreate celery-worker
elif [ "$FORCE_RECREATE" = true ]; then
    echo "[3/4] 强制重建 Celery Worker 容器（使用 python:3.11 基础镜像，会重新安装依赖）..."
    docker-compose -f docker-compose.dev.yml up -d --force-recreate celery-worker
else
    echo "[3/4] 重启 Celery Worker 容器（使用 python:3.11 基础镜像 + volumes 挂载）..."
    docker-compose -f docker-compose.dev.yml restart celery-worker
fi
WORKER_CONTAINER_ID=$(docker ps -q -f name=finnews_celery_worker)
echo "Worker 容器已重启 (Container ID: $WORKER_CONTAINER_ID)"

# 等待 Worker 启动
sleep 3

# 重启 Celery Beat 容器
echo ""
if [ "$REBUILD_IMAGE" = true ]; then
    echo "[5/5] 强制重建 Celery Beat 容器（使用 python:3.11 基础镜像 + volumes 挂载）..."
    docker-compose -f docker-compose.dev.yml up -d --force-recreate celery-beat
elif [ "$FORCE_RECREATE" = true ]; then
    echo "[4/4] 强制重建 Celery Beat 容器（使用 python:3.11 基础镜像，会重新安装依赖）..."
    docker-compose -f docker-compose.dev.yml up -d --force-recreate celery-beat
else
    echo "[4/4] 重启 Celery Beat 容器（使用 python:3.11 基础镜像 + volumes 挂载）..."
    docker-compose -f docker-compose.dev.yml restart celery-beat
fi
BEAT_CONTAINER_ID=$(docker ps -q -f name=finnews_celery_beat)
echo "Beat 容器已重启 (Container ID: $BEAT_CONTAINER_ID)"

cd "$SCRIPT_DIR"

echo ""
echo "============================================"
echo "  Celery 容器重启成功！"
echo "============================================"
echo ""
echo "容器信息:"
echo "   - Worker Container ID: $WORKER_CONTAINER_ID"
echo "   - Beat Container ID: $BEAT_CONTAINER_ID"
echo ""
echo "查看日志命令:"
echo "   - Worker 日志: docker logs -f finnews_celery_worker"
echo "   - Beat 日志: docker logs -f finnews_celery_beat"
echo "   - 最近100行: docker logs --tail 100 finnews_celery_worker"
echo ""
echo "监控命令:"
echo "   - 查看任务列表: curl http://localhost:8000/api/v1/tasks/"
echo "   - 查看容器状态: docker ps | grep celery"
echo ""
echo "实时监控已启动，每1分钟自动爬取新闻"
echo ""
echo "说明:"
echo "   - 容器使用 python:3.11 基础镜像 + volumes 挂载代码"
echo "   - 每次启动容器都会执行 pip install 安装依赖"
echo "   - 构建的镜像（deploy-celery-worker/beat）不会被使用，可以删除释放空间"
echo ""
echo "停止服务:"
echo "   cd ../deploy && docker-compose -f docker-compose.dev.yml stop celery-worker celery-beat"
echo ""
echo "完全重启（重建容器，会重新安装依赖）:"
echo "   cd ../deploy && docker-compose -f docker-compose.dev.yml up -d --force-recreate celery-worker celery-beat"
echo ""
echo "============================================"

if [ "$SHOW_LOGS" = true ]; then
    echo ""
    echo "正在监控日志（按 Ctrl+C 退出）..."
    echo ""
    sleep 2
    docker logs -f --tail 50 finnews_celery_worker
fi

