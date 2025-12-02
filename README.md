# FinnewsHunter：金融新闻驱动的多智能体投资决策平台

![FinnewsHunter Logo](assets/images/FINNEWS_HUNTER.png)

基于 [AgenticX](https://github.com/DemonDamon/AgenticX) 框架构建的企业级金融新闻分析系统，融合实时新闻流、深度量化分析和多智能体辩论机制。

---

## 🎯 项目特色

- ✅ **AgenticX 原生**: 深度集成 AgenticX 框架，使用 Agent、Tool、Workflow 等核心抽象
- ✅ **智能体驱动**: NewsAnalyst 智能体自动分析新闻情感和市场影响
- ✅ **完整技术栈**: FastAPI + PostgreSQL + Milvus + Redis + React
- ✅ **生产就绪**: Docker Compose 一键部署，日志、监控完备

---

## 🏗️ 系统架构

![FinnewsHunter Architecture](assets/images/arch-20251201.png)

系统采用分层架构设计：
- **M6 前端交互层**: React + TypeScript + Shadcn UI
- **M1 平台服务层**: FastAPI Gateway + Task Manager
- **M4/M5 智能体协同层**: AgenticX Agent + Debate Workflow
- **M2/M3 基础设施层**: Crawler Service + LLM Service + Embedding
- **M7-M11 存储与学习层**: PostgreSQL + Milvus + Redis + ACE Framework

---

## 🚀 快速开始

### 前置条件

- Python 3.11+
- Docker & Docker Compose
- (可选) OpenAI API Key 或本地 LLM

### 1. 安装 AgenticX

```bash
cd /Users/damon/myWork/AgenticX
pip install -e .
```

### 2. 安装依赖

```bash
cd examples/agenticx-for-finance/FinnewsHunter/backend
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp env.example .env
# 编辑 .env 文件，填入 OPENAI_API_KEY 等配置
```

### 4. 启动服务

```bash
# 方式 1: 使用启动脚本（推荐）
chmod +x start.sh
./start.sh

# 方式 2: 手动启动
cd ../deploy
docker-compose -f docker-compose.dev.yml up -d
cd ../backend
python -m app.core.database  # 初始化数据库
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 访问应用

- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **前端界面**: 直接打开 `frontend/index.html`

---

## 📚 使用指南

### 步骤 1: 爬取新闻

**方式 1: 通过前端**
1. 打开 `frontend/index.html`
2. 输入页码范围（如 1-3）
3. 点击"📰 爬取新闻"

**方式 2: 通过 API**
```bash
curl -X POST http://localhost:8000/api/v1/news/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "source": "sina",
    "start_page": 1,
    "end_page": 2
  }'
```

### 步骤 2: 查看新闻列表

```bash
curl http://localhost:8000/api/v1/news/?limit=10
```

### 步骤 3: 分析新闻

**方式 1: 通过前端**
- 在新闻卡片上点击"📊 分析"按钮

**方式 2: 通过 API**
```bash
curl -X POST http://localhost:8000/api/v1/analysis/news/1
```

### 步骤 4: 查看分析结果

```bash
curl http://localhost:8000/api/v1/analysis/1
```

---

## 🏗️ 项目结构

```
FinnewsHunter/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── agents/            # 智能体定义（NewsAnalyst）
│   │   ├── api/               # FastAPI 路由
│   │   ├── core/              # 核心配置（config, database）
│   │   ├── models/            # SQLAlchemy 数据模型
│   │   ├── services/          # 业务服务（LLM, Embedding, Analysis）
│   │   ├── storage/           # 存储封装（Milvus）
│   │   └── tools/             # AgenticX 工具（Crawler, Cleaner）
│   ├── requirements.txt       # Python 依赖
│   └── start.sh              # 启动脚本
├── deploy/                    # 部署配置
│   └── docker-compose.dev.yml # Docker Compose 配置
├── frontend/                  # 前端界面（MVP）
│   └── index.html            # 简化版前端
└── legacy_v1/                # 原始代码（已迁移）
```

---

## 🧪 测试与验收

### MVP 验收标准

- [x] 新闻爬取成功并存入 PostgreSQL
- [ ] NewsAnalyst 调用 LLM 完成分析
- [ ] 分析结果包含情感评分
- [ ] 前端能够展示新闻和分析结果

### 测试流程

1. **启动所有服务**
   ```bash
   ./start.sh
   ```

2. **检查 Docker 容器状态**
   ```bash
   docker ps
   # 应看到: postgres, redis, milvus-standalone, milvus-etcd, milvus-minio
   ```

3. **测试新闻爬取**
   ```bash
   curl -X POST http://localhost:8000/api/v1/news/crawl \
     -H "Content-Type: application/json" \
     -d '{"source": "sina", "start_page": 1, "end_page": 1}'
   
   # 等待 5-10 秒后查看结果
   curl http://localhost:8000/api/v1/news/?limit=5
   ```

4. **测试智能体分析**
   ```bash
   # 获取第一条新闻的ID
   NEWS_ID=$(curl -s http://localhost:8000/api/v1/news/?limit=1 | jq '.[0].id')
   
   # 触发分析
   curl -X POST http://localhost:8000/api/v1/analysis/news/$NEWS_ID
   
   # 查看分析结果
   curl http://localhost:8000/api/v1/analysis/1
   ```

5. **测试前端界面**
   - 打开 `frontend/index.html`
   - 点击"爬取新闻"并等待完成
   - 选择一条新闻点击"分析"
   - 查看情感评分是否显示

---

## 🔧 故障排查

### 问题 1: 数据库连接失败

```bash
# 检查 PostgreSQL 是否启动
docker ps | grep postgres

# 查看日志
docker logs finnews_postgres

# 重启容器
docker-compose -f deploy/docker-compose.dev.yml restart postgres
```

### 问题 2: LLM 调用失败

检查 `.env` 文件中的 API Key 配置：
```bash
# 确保设置了 OPENAI_API_KEY
grep OPENAI_API_KEY backend/.env
```

### 问题 3: Milvus 连接失败

```bash
# Milvus 需要较长启动时间（约 60 秒）
docker logs finnews_milvus

# 等待健康检查通过
docker inspect finnews_milvus | grep Health
```

### 问题 4: 前端 CORS 错误

确保后端 `core/config.py` 中的 CORS 配置包含前端地址：
```python
BACKEND_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:8000"]
```

---

## 📊 数据库结构

### News（新闻表）
- id, title, content, url, source
- publish_time, stock_codes
- sentiment_score, is_embedded

### Analysis（分析表）
- id, news_id, agent_name
- sentiment, sentiment_score, confidence
- analysis_result, structured_data

### Stock（股票表）
- id, code, name, industry, market

---

## 🛠️ 开发指南

### 添加新的爬虫

1. 继承 `BaseCrawler` 类
2. 实现 `crawl()` 方法
3. 注册到 `tools/__init__.py`

示例：
```python
# backend/app/tools/custom_crawler.py
from .crawler_base import BaseCrawler

class CustomCrawlerTool(BaseCrawler):
    name = "custom_crawler"
    
    def crawl(self, start_page, end_page):
        # 实现爬取逻辑
        pass
```

### 添加新的智能体

1. 继承 `Agent` 类
2. 定义 role、goal、backstory
3. 实现业务方法

示例：
```python
# backend/app/agents/risk_analyst.py
from agenticx import Agent

class RiskAnalystAgent(Agent):
    def __init__(self, llm_provider):
        super().__init__(
            name="RiskAnalyst",
            role="风险分析师",
            goal="评估投资风险",
            llm_provider=llm_provider
        )
```

---

## 📈 路线图

### Phase 1: MVP（已完成） ✅
- [x] 项目基础设施
- [x] 数据库模型
- [x] 爬虫工具重构
- [x] LLM 服务集成
- [x] NewsAnalyst 智能体
- [x] FastAPI 路由
- [x] 简化版前端

### Phase 2: 多智能体协作（计划中）
- [ ] BullResearcher & BearResearcher 智能体
- [ ] 基于 `agenticx.collaboration.Debate` 的辩论工作流
- [ ] 实时 WebSocket 推送
- [ ] 智能体执行轨迹可视化

### Phase 3: 知识增强（计划中）
- [ ] 金融知识图谱（Neo4j）
- [ ] 智能体记忆系统
- [ ] GraphRetriever 图检索

### Phase 4: 自我进化（计划中）
- [ ] ACE 框架集成
- [ ] 投资策略 Playbook
- [ ] 决策效果评估与学习

---

## 📄 许可证

本项目遵循 AgenticX 的许可证。

---

## 🙏 致谢

- [AgenticX](https://github.com/yourusername/AgenticX) - 多智能体框架
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [Milvus](https://milvus.io/) - 向量数据库
- [阿里云百炼](https://dashscope.console.aliyun.com/) - LLM 服务
- [Shadcn UI](https://ui.shadcn.com/) - 前端组件库

---

## ⭐ Star History

如果你觉得这个项目对你有帮助，欢迎给个 Star ⭐️！

[![Star History Chart](https://api.star-history.com/svg?repos=DemonDamon/Listed-company-news-crawl-and-text-analysis&type=Date)](https://star-history.com/#DemonDamon/Listed-company-news-crawl-and-text-analysis&Date)

---

**Built with ❤️ using AgenticX**

