#!/bin/bash
set -e

# 开发环境：检查依赖是否已安装（通过检查关键包）
# 注意：由于 volumes 挂载会覆盖 /app，构建时安装的依赖可能不可见
# 这个脚本确保在开发环境中依赖总是可用的
CHECK_PACKAGES=("celery" "fastapi" "sqlalchemy")
NEED_INSTALL=false

for pkg in "${CHECK_PACKAGES[@]}"; do
    if ! python -c "import ${pkg}" 2>/dev/null; then
        NEED_INSTALL=true
        break
    fi
done

if [ "$NEED_INSTALL" = true ]; then
    echo "📦 [开发环境] 检测到依赖未安装，正在安装..."
    echo "   提示：这是因为 volumes 挂载覆盖了镜像中的依赖"
    pip install --no-cache-dir -r requirements.txt
    echo "✅ 依赖安装完成"
else
    echo "✅ 依赖已存在，跳过安装"
fi

# 执行传入的命令
exec "$@"
