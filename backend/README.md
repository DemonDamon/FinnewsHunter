# FinnewsHunter Backend

基于 AgenticX 框架的金融新闻智能分析系统后端服务。

## 📚 文档导航

### 快速开始
- **[QUICKSTART.md](../QUICKSTART.md)** - 快速启动指南（推荐新手阅读）

### 配置指南
- **[CONFIG_GUIDE.md](CONFIG_GUIDE.md)** - **统一配置指南**（推荐首选）
  - 一个配置文件支持所有 LLM 服务商
  - 快速切换 OpenAI / 百炼 / 代理
  - 包含场景示例和工作原理
  
- **[env.example](env.example)** - 配置模板（包含所有场景的注释）

### 专项配置
- **[BAILIAN_SETUP.md](BAILIAN_SETUP.md)** - 阿里云百炼详细配置（国内用户推荐）
- **[API_PROXY_GUIDE.md](API_PROXY_GUIDE.md)** - API 代理配置详解

---

## 🚀 快速配置

### 方法 1: 交互式脚本（推荐）

```bash
chmod +x setup_env.sh
./setup_env.sh

# 按提示选择：
# 1) OpenAI 官方
# 2) 阿里云百炼（推荐国内用户）
# 3) 其他代理
# 4) 手动配置
```

### 方法 2: 手动配置

```bash
cp env.example .env
nano .env  # 根据注释选择配置方案
```

---

## 📦 主要功能

- **多智能体系统**：基于 AgenticX 框架
  - NewsAnalyst：新闻分析智能体
  - 更多智能体开发中...

- **数据采集**：
  - 新浪财经爬虫
  - 金融界爬虫

- **存储系统**：
  - PostgreSQL：关系数据存储
  - Milvus：向量数据库
  - Redis：缓存和任务队列

- **LLM 支持**：
  - OpenAI (GPT-3.5/GPT-4)
  - 阿里云百炼（通义千问）
  - 其他 OpenAI 兼容服务

---

## 🏗️ 项目结构

```
backend/
├── app/
│   ├── agents/          # 智能体定义
│   ├── api/             # FastAPI 路由
│   ├── core/            # 核心配置
│   ├── models/          # 数据模型
│   ├── services/        # 业务服务
│   ├── storage/         # 存储封装
│   └── tools/           # 爬虫和工具
├── logs/                # 日志文件
├── tests/               # 测试文件
├── .env                 # 环境配置（从 env.example 复制）
├── env.example          # 配置模板
├── requirements.txt     # Python 依赖
└── start.sh            # 启动脚本
```

---

## 🛠️ 开发指南

### 启动开发环境

```bash
# 1. 配置环境变量
./setup_env.sh

# 2. 启动服务（包括 Docker 容器）
./start.sh
```

### 测试导入

```bash
python test_imports.py
```

### 查看日志

```bash
tail -f logs/finnews.log
```

---

## 🔧 常用配置场景

### OpenAI 官方
```bash
LLM_MODEL=gpt-3.5-turbo
OPENAI_API_KEY=sk-openai-key
MILVUS_DIM=1536
```

### 阿里云百炼（推荐国内）
```bash
LLM_MODEL=qwen-plus
OPENAI_API_KEY=sk-bailian-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MILVUS_DIM=1024
```

### OpenAI 代理
```bash
LLM_MODEL=gpt-3.5-turbo
OPENAI_API_KEY=sk-proxy-key
OPENAI_BASE_URL=https://your-proxy.com/v1
MILVUS_DIM=1536
```

详细说明见 **[CONFIG_GUIDE.md](CONFIG_GUIDE.md)**

---

## 📝 API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可

MIT License

