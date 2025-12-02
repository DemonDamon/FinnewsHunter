# 阿里云百炼配置指南

## 为什么选择百炼？

✅ **国内访问**：无需科学上网，稳定快速  
✅ **性价比高**：比 OpenAI 便宜 60-70%  
✅ **中文优化**：通义千问对中文理解更好  
✅ **合规性**：符合国内数据安全要求

---

## 快速配置（2 步）

### 步骤 1: 获取 API Key

1. 访问：https://dashscope.console.aliyun.com/
2. 登录/注册阿里云账号
3. 创建 API Key（格式：`sk-xxxxxx`）

### 步骤 2: 运行配置脚本

```bash
cd backend

# 运行交互式配置脚本
chmod +x setup_env.sh
./setup_env.sh

# 选择选项 2（阿里云百炼）
# 填入你的 API Key
```

**就这么简单！** 脚本会自动生成正确的配置。

---

## 手动配置方式

如果你喜欢手动配置，编辑 `.env` 文件：

```bash
# 1. LLM 配置（OpenAI 兼容模式）
LLM_PROVIDER=openai                                         # 使用 openai（兼容协议）
LLM_MODEL=qwen-plus                                         # 百炼模型名称
OPENAI_API_KEY=sk-your-bailian-key                         # 百炼的 API Key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # 百炼端点

# 2. Embedding 配置
EMBEDDING_PROVIDER=openai                                   # 同样使用 openai 兼容模式
EMBEDDING_MODEL=text-embedding-v4                          # 百炼 embedding 模型

# 3. ⚠️ 重要：修改向量维度
MILVUS_DIM=1024                                            # text-embedding-v4 是 1024 维
```

**为什么 LLM_PROVIDER=openai？**  
因为百炼提供了 OpenAI 兼容的 API，设置 `OPENAI_BASE_URL` 后，请求会自动发往百炼，而不是 OpenAI。详见 `env.example` 文件的注释。

---

## 完整配置示例

```bash
# LLM 配置
LLM_PROVIDER=openai
LLM_MODEL=qwen-plus
OPENAI_API_KEY=sk-xxxxxxxxxxxxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Embedding 配置
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_BATCH_SIZE=100

# ⚠️ 向量维度必须匹配
MILVUS_DIM=1024
```

---

## 模型选择指南

### LLM 模型对比

| 模型 | 用途 | 速度 | 效果 | 价格 |
|------|------|------|------|------|
| **qwen-turbo** | 简单任务 | ⚡️⚡️⚡️ | ⭐️⭐️⭐️ | ¥ |
| **qwen-plus** | 日常使用（推荐） | ⚡️⚡️ | ⭐️⭐️⭐️⭐️ | ¥¥ |
| **qwen-max** | 复杂分析 | ⚡️ | ⭐️⭐️⭐️⭐️⭐️ | ¥¥¥ |
| **qwen-long** | 长文本（128K） | ⚡️ | ⭐️⭐️⭐️⭐️ | ¥¥ |

### Embedding 模型对比

| 模型 | 维度 | 用途 | 说明 |
|------|------|------|------|
| text-embedding-v1 | 1536 | 基础版 | 兼容性好 |
| text-embedding-v2 | 1536 | 标准版 | 效果提升 |
| text-embedding-v3 | 1024 | 高效版 | 速度快 |
| **text-embedding-v4** | **1024** | **推荐** | **最新，效果最好** |

---

## ⚠️ 重要注意事项

### 1. 向量维度配置

不同的 embedding 模型有不同的向量维度：

```bash
# OpenAI ada-002：1536 维
EMBEDDING_MODEL=text-embedding-ada-002
MILVUS_DIM=1536

# 百炼 v4：1024 维
EMBEDDING_MODEL=text-embedding-v4
MILVUS_DIM=1024
```

**如果维度不匹配，向量存储会失败！**

### 2. 首次启动时清空数据库

如果之前使用过其他 embedding 模型，需要重建 Milvus 集合：

```bash
# 停止服务
docker-compose -f deploy/docker-compose.dev.yml down

# 删除 Milvus 数据
docker volume rm deploy_milvus_data

# 重新启动
./start.sh
```

### 3. API Key 权限

确保你的 API Key 有以下权限：
- ✅ 通义千问（LLM）
- ✅ 文本向量（Embedding）

在 DashScope 控制台可以查看和设置权限。

---

## 性能优化建议

### 1. 批量处理

百炼支持批量 embedding，提高吞吐量：

```bash
EMBEDDING_BATCH_SIZE=100  # 最多 100 条/批
```

### 2. 选择合适的模型

- **新闻分析**：`qwen-plus`（平衡速度和效果）
- **情感分析**：`qwen-turbo`（速度优先）
- **深度报告**：`qwen-max`（效果优先）

### 3. 缓存配置

FinnewsHunter 已集成 Redis 缓存，相同文本的 embedding 会自动缓存：

```bash
NEWS_CACHE_TTL=3600  # 1小时缓存
```

---

## 费用估算

以 1000 条新闻分析为例：

### LLM 费用（qwen-plus）
- 输入：500 token/条 × 1000 = 500K tokens
- 输出：200 token/条 × 1000 = 200K tokens
- **费用**：约 ¥10-15

### Embedding 费用（text-embedding-v4）
- 平均：300 token/条 × 1000 = 300K tokens
- **费用**：约 ¥0.5-1

**总计**：约 **¥10-16 / 1000条新闻**

比 OpenAI 便宜约 **60-70%**！

---

## 测试配置

### 测试 1: 健康检查

```bash
curl http://localhost:8000/health
```

### 测试 2: 爬取新闻

```bash
curl -X POST http://localhost:8000/api/v1/news/crawl \
  -H "Content-Type: application/json" \
  -d '{"source": "sina", "start_page": 1, "end_page": 1}'
```

### 测试 3: LLM 分析

```bash
# 获取新闻 ID
NEWS_ID=$(curl -s http://localhost:8000/api/v1/news/?limit=1 | jq -r '.[0].id')

# 触发分析（会调用百炼 LLM）
curl -X POST http://localhost:8000/api/v1/analysis/news/$NEWS_ID | jq
```

如果返回分析结果，说明配置成功！

---

## 常见问题

### Q1: 提示 "Invalid API Key"

**解决方案**:
1. 检查 API Key 是否正确复制
2. 确认 API Key 已启用
3. 检查账户余额是否充足

### Q2: 向量存储失败

**错误信息**: `dimension mismatch`

**解决方案**:
```bash
# 确保维度配置正确
grep MILVUS_DIM .env
# 应该显示：MILVUS_DIM=1024

# 如果不正确，修改后重建数据库
docker-compose -f deploy/docker-compose.dev.yml down -v
./start.sh
```

### Q3: 调用速度慢

**优化建议**:
1. 使用 `qwen-turbo` 模型（更快）
2. 减少 `LLM_MAX_TOKENS`
3. 使用批量接口

### Q4: 想混合使用 OpenAI 和百炼

**配置方案**:

```bash
# LLM 使用 OpenAI（效果好）
LLM_PROVIDER=openai
LLM_MODEL=gpt-3.5-turbo
OPENAI_API_KEY=sk-openai-key
OPENAI_BASE_URL=  # 留空使用官方 API

# Embedding 使用百炼（便宜）
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# 注意：这种混用需要在代码中分别配置，不推荐
```

---

## 相关链接

- 🔗 [百炼控制台](https://dashscope.console.aliyun.com/)
- 📖 [通义千问文档](https://help.aliyun.com/zh/model-studio/developer-reference/quick-start)
- 💰 [计费说明](https://help.aliyun.com/zh/model-studio/pricing)
- 🎓 [最佳实践](https://help.aliyun.com/zh/model-studio/use-cases)

---

**配置完成后，您就可以享受快速、稳定、经济的 AI 服务了！🎉**

