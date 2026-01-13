# FinnewsHunter Backend

基于 AgenticX 框架的金融新闻智能分析系统后端服务。

## 文档导航

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

## 快速配置

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

## 主要功能

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

## 项目结构

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

## 开发指南

### 启动开发环境

```bash
# 1. 配置环境变量
./setup_env.sh

# 2. 启动服务（包括 Docker 容器）
./start.sh
```

### 工具脚本

项目提供了一些实用工具脚本，位于 `tests/` 目录下：

```bash
# 检查 Milvus 向量存储数据
python tests/check_milvus_data.py

# 检查新闻向量化状态
python tests/check_news_embedding_status.py

# 手动向量化指定新闻（用于修复未向量化的新闻）
python tests/manual_vectorize.py <news_id>
```

### 查看日志

```bash
tail -f logs/finnews.log
```

---

## 常用配置场景

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

## API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 手动触发爬取

如果某个新闻源显示为空，可以手动触发实时爬取：

```bash
# 触发腾讯财经爬取
curl -X POST "http://localhost:8000/api/v1/tasks/realtime" \
  -H "Content-Type: application/json" \
  -d '{"source": "tencent", "force_refresh": true}'

# 触发经济观察网爬取
curl -X POST "http://localhost:8000/api/v1/tasks/realtime" \
  -H "Content-Type: application/json" \
  -d '{"source": "eeo", "force_refresh": true}'
```

支持的新闻源：
- `sina` - 新浪财经
- `tencent` - 腾讯财经
- `eeo` - 经济观察网
- `jwview` - 金融界
- `caijing` - 财经网
- `jingji21` - 21经济网
- `nbd` - 每日经济新闻
- `yicai` - 第一财经
- `163` - 网易财经
- `eastmoney` - 东方财富

### 故障排查

如果文档页面显示空白或一直加载：

1. **检查浏览器控制台**：按 F12 打开开发者工具，查看 Console 和 Network 标签页是否有错误
2. **尝试 ReDoc**：如果 Swagger UI 无法加载，尝试访问 ReDoc（使用不同的 CDN）
3. **清除浏览器缓存**：按 `Ctrl+Shift+R` (Windows/Linux) 或 `Cmd+Shift+R` (Mac) 强制刷新
4. **检查网络连接**：文档页面需要从 CDN 加载 JavaScript 资源，确保网络连接正常
5. **检查后端服务**：确保后端服务正在运行，可以访问 http://localhost:8000/health 验证
