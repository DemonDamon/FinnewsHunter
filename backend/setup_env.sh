#!/bin/bash
# 环境变量快速配置脚本

echo "============================================"
echo "  FinnewsHunter 环境配置向导"
echo "============================================"
echo ""
echo "请选择 LLM 服务商："
echo "  1) OpenAI 官方（默认）"
echo "  2) 阿里云百炼（推荐国内用户）"
echo "  3) 其他 OpenAI 代理"
echo "  4) 手动配置（复制模板）"
echo ""
read -p "请输入选项 (1-4) [默认:1]: " choice
choice=${choice:-1}

case $choice in
  1)
    # OpenAI 官方
    cat > .env << 'EOF'
# FinnewsHunter 环境配置
APP_NAME=FinnewsHunter
DEBUG=True

POSTGRES_USER=finnews
POSTGRES_PASSWORD=finnews_dev_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=finnews_db

REDIS_HOST=localhost
REDIS_PORT=6379

MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DIM=1536

# OpenAI 官方配置
LLM_PROVIDER=openai
LLM_MODEL=gpt-3.5-turbo
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
OPENAI_API_KEY=sk-your-openai-api-key-here

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002

LOG_LEVEL=INFO
EOF
    echo ""
    echo "✅ OpenAI 配置已创建"
    echo "📝 请编辑 .env 并填入你的 OPENAI_API_KEY"
    ;;
    
  2)
    # 阿里云百炼
    cat > .env << 'EOF'
# FinnewsHunter 环境配置
APP_NAME=FinnewsHunter
DEBUG=True

POSTGRES_USER=finnews
POSTGRES_PASSWORD=finnews_dev_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=finnews_db

REDIS_HOST=localhost
REDIS_PORT=6379

MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DIM=1024

# 阿里云百炼配置（OpenAI 兼容模式）
LLM_PROVIDER=openai
LLM_MODEL=qwen-plus
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
OPENAI_API_KEY=sk-your-bailian-api-key-here
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-v4

LOG_LEVEL=INFO
EOF
    echo ""
    echo "✅ 百炼配置已创建"
    echo "📝 请编辑 .env 并填入你的百炼 API Key"
    echo "🔗 获取 Key: https://dashscope.console.aliyun.com/"
    ;;
    
  3)
    # 其他代理
    cat > .env << 'EOF'
# FinnewsHunter 环境配置
APP_NAME=FinnewsHunter
DEBUG=True

POSTGRES_USER=finnews
POSTGRES_PASSWORD=finnews_dev_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=finnews_db

REDIS_HOST=localhost
REDIS_PORT=6379

MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_DIM=1536

# OpenAI 代理配置
LLM_PROVIDER=openai
LLM_MODEL=gpt-3.5-turbo
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
OPENAI_API_KEY=sk-your-proxy-api-key
OPENAI_BASE_URL=https://your-proxy.com/v1

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002

LOG_LEVEL=INFO
EOF
    echo ""
    echo "✅ 代理配置已创建"
    echo "📝 请编辑 .env 并填入你的代理信息"
    ;;
    
  4)
    # 手动配置
    cp env.example .env
    echo ""
    echo "✅ 配置模板已复制"
    echo "📝 请编辑 .env 并选择合适的配置方案"
    ;;
    
  *)
    echo "❌ 无效选项"
    exit 1
    ;;
esac

echo ""
read -p "是否现在编辑配置文件？(Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    ${EDITOR:-nano} .env
fi

echo ""
echo "✨ 配置完成！运行 ./start.sh 启动服务"

