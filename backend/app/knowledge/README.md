# 知识图谱模块

## 📊 概述

知识图谱模块为每只股票构建动态的知识图谱，用于智能化的新闻检索和分析。

## 🎯 核心功能

### 1. 多维度知识建模

为每家公司建立包含以下信息的知识图谱：

- **名称变体**：公司简称、别名、全称
- **业务线**：主营业务、新增业务、已停止业务
- **行业归属**：一级行业、二级行业、细分领域
- **产品服务**：主要产品和服务
- **关联概念**：涉及的热点概念（AI大模型、云计算等）
- **检索关键词**：优化检索效果的关键词

### 2. 智能并发检索

基于知识图谱生成多样化的检索查询，并发调用搜索API：

```
示例：彩讯股份 (300634)

生成的查询组合：
1. "彩讯股份 300634"
2. "彩讯 股票"
3. "彩讯股份 运营商增值服务"
4. "彩讯 AI大模型应用"
5. "彩讯科技 云计算"
6. ...（最多10条并发查询）
```

### 3. 动态图谱更新

- **构建时机**：首次定向爬取时自动构建
- **数据来源**：
  - akshare：基础信息（行业、市值、主营业务）
  - LLM推理：名称变体、业务细分
  - 新闻分析：业务变化、新概念
  - 文档解析：深度信息（年报、公告）
- **更新机制**：每次定向爬取后自动更新

## 🏗️ 架构设计

### 图谱结构

```
(Company) 公司节点
   ├─ HAS_VARIANT ─> (NameVariant) 名称变体
   ├─ OPERATES_IN ─> (Business) 业务线
   ├─ BELONGS_TO  ─> (Industry) 行业
   ├─ PROVIDES    ─> (Product) 产品
   ├─ RELATES_TO  ─> (Keyword) 关键词
   └─ INVOLVES    ─> (Concept) 概念
```

### 核心组件

1. **graph_models.py** - 数据模型定义
2. **graph_service.py** - 图谱CRUD服务
3. **knowledge_extractor.py** - 知识提取Agent
4. **parallel_search.py** - 并发检索策略

## 🚀 使用方法

### 1. 启动 Neo4j

```bash
cd deploy
docker-compose -f docker-compose.dev.yml up -d neo4j
```

### 2. 初始化图谱

```bash
cd backend
python init_knowledge_graph.py
```

### 3. API 调用

#### 查询图谱
```bash
GET /api/v1/knowledge-graph/{stock_code}
```

#### 构建图谱
```bash
POST /api/v1/knowledge-graph/{stock_code}/build
{
  "force_rebuild": false
}
```

#### 更新图谱
```bash
POST /api/v1/knowledge-graph/{stock_code}/update
{
  "update_from_news": true,
  "news_limit": 20
}
```

#### 删除图谱
```bash
DELETE /api/v1/knowledge-graph/{stock_code}
```

### 4. 自动集成

定向爬取时自动使用知识图谱：

1. **检查图谱**：如果不存在，自动从 akshare + LLM 构建
2. **并发检索**：基于图谱生成的多个关键词并发搜索
3. **更新图谱**：爬取完成后，从新闻中提取新信息更新图谱

## 📈 效果对比

### 传统单关键词检索

```python
query = "彩讯股份 股票 300634"
results = search(query)  # ~20-30条
```

### 基于知识图谱的并发检索

```python
queries = [
    "彩讯股份 300634",
    "彩讯 运营商增值服务",
    "彩讯股份 AI大模型应用",
    "彩讯科技 云计算",
    ...
]
results = parallel_search(queries)  # ~100-200条，去重后70-130条
```

**召回率提升：3-5倍**

## 🔧 配置

环境变量：
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=finnews_neo4j_password
```

## 📊 监控

访问 Neo4j 浏览器：
- URL: http://localhost:7474
- 用户名: neo4j
- 密码: finnews_neo4j_password

示例查询：
```cypher
// 查看所有公司
MATCH (c:Company) RETURN c

// 查看公司的完整图谱
MATCH (c:Company {stock_code: 'SZ300634'})-[r]->(n)
RETURN c, r, n

// 查看业务线
MATCH (c:Company)-[:OPERATES_IN]->(b:Business)
WHERE b.status = 'active'
RETURN c.stock_name, b.business_name, b.status
```

## ⚠️ 注意事项

1. **LLM成本**：图谱构建和更新会调用LLM，注意API成本
2. **并发限制**：并发检索默认5个worker，可根据API限制调整
3. **图谱更新**：建议每次定向爬取后自动更新，保持图谱时效性
4. **数据质量**：LLM提取的信息需要人工review，建议提供review接口

