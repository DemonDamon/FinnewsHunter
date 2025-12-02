# API 代理配置指南

## 概述

FinnewsHunter 支持使用第三方 API 转发服务，这对于以下场景特别有用：
- 🌍 网络访问受限，需要使用代理
- 💰 使用国内或其他地区的 OpenAI 代理服务
- 🔄 使用自建的 API 转发服务
- 🎯 使用兼容 OpenAI API 的其他服务

---

## 配置方法

在 `.env` 文件中添加 `*_BASE_URL` 配置项：

```bash
# OpenAI 官方 API（默认）
OPENAI_API_KEY=sk-your-key-here
# OPENAI_BASE_URL=https://api.openai.com/v1

# 使用第三方代理
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://your-proxy.com/v1
```

---

## 常见配置示例

### 1. OpenAI 第三方代理

#### 示例 1: 使用 OpenAI-SB（国内代理）
```bash
OPENAI_API_KEY=sb-your-key-here
OPENAI_BASE_URL=https://api.openai-sb.com/v1
```

#### 示例 2: 使用 CloseAI（国内代理）
```bash
OPENAI_API_KEY=your-key-here
OPENAI_BASE_URL=https://api.closeai-asia.com/v1
```

#### 示例 3: 使用自建 Nginx 代理
```bash
OPENAI_API_KEY=sk-your-original-key
OPENAI_BASE_URL=https://your-domain.com/openai/v1
```

### 2. 兼容 OpenAI API 的其他服务

#### 示例 1: Azure OpenAI
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-35-turbo  # Azure 的模型名称
OPENAI_API_KEY=your-azure-key
OPENAI_BASE_URL=https://your-resource.openai.azure.com/openai/deployments/your-deployment
```

#### 示例 2: 通义千问（Qwen）兼容模式
```bash
LLM_PROVIDER=openai  # 使用兼容模式
LLM_MODEL=qwen-turbo
OPENAI_API_KEY=sk-your-qwen-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

#### 示例 3: 本地 Ollama
```bash
LLM_PROVIDER=ollama
LLM_MODEL=llama2
OPENAI_BASE_URL=http://localhost:11434/v1
```

### 3. Claude (Anthropic) 代理

```bash
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-sonnet-20240229
ANTHROPIC_API_KEY=your-key
ANTHROPIC_BASE_URL=https://your-anthropic-proxy.com
```

---

## 完整配置示例

### 场景 1: 国内用户使用 OpenAI 代理

```bash
# .env 文件
APP_NAME=FinnewsHunter
DEBUG=True

# 数据库（使用默认配置）
POSTGRES_HOST=localhost
REDIS_HOST=localhost
MILVUS_HOST=localhost

# LLM 配置（使用国内代理）
LLM_PROVIDER=openai
LLM_MODEL=gpt-3.5-turbo
OPENAI_API_KEY=sk-your-proxy-key-here
OPENAI_BASE_URL=https://api.openai-sb.com/v1

# Embedding 使用相同代理
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002
```

### 场景 2: 使用阿里云通义千问

```bash
# LLM 配置
LLM_PROVIDER=openai  # 使用 OpenAI 兼容模式
LLM_MODEL=qwen-turbo
OPENAI_API_KEY=sk-your-qwen-api-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Embedding 使用通义千问
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-v1
```

### 场景 3: 本地部署 + 云端 API 混合

```bash
# LLM 使用本地 Ollama（快速响应）
LLM_PROVIDER=ollama
LLM_MODEL=llama2
OPENAI_BASE_URL=http://localhost:11434/v1

# Embedding 使用云端（效果更好）
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002
OPENAI_API_KEY=sk-your-openai-key
# Embedding 不设置 base_url，使用官方 API
```

---

## 验证配置

### 方法 1: 测试导入
```bash
cd backend
python test_imports.py
```

### 方法 2: 测试 API 调用
```bash
# 启动服务器
uvicorn app.main:app --reload

# 在另一个终端测试
curl -X POST http://localhost:8000/api/v1/news/crawl \
  -H "Content-Type: application/json" \
  -d '{"source": "sina", "start_page": 1, "end_page": 1}'

# 等待几秒后，尝试分析
NEWS_ID=$(curl -s http://localhost:8000/api/v1/news/?limit=1 | jq -r '.[0].id')
curl -X POST http://localhost:8000/api/v1/analysis/news/$NEWS_ID
```

如果分析成功，说明 LLM 配置正确。

### 方法 3: 直接测试 LLM 连接
```python
# test_llm.py
from app.services.llm_service import get_llm_service

llm = get_llm_service()
response = llm.generate("你好，请用一句话介绍自己。")
print(response)
```

---

## 常见问题

### Q1: 代理配置后仍然无法连接？

**检查清单**:
1. Base URL 格式是否正确（需要包含 `/v1` 后缀）
2. API Key 是否有效
3. 代理服务是否正常运行
4. 网络是否可以访问代理地址

**测试代理连接**:
```bash
# 使用 curl 测试
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://your-proxy.com/v1/models
```

### Q2: 如何切换不同的 LLM 提供商？

只需修改 `.env` 文件：

```bash
# 从 OpenAI 切换到 Claude
LLM_PROVIDER=anthropic  # 改为 anthropic
LLM_MODEL=claude-3-sonnet-20240229
ANTHROPIC_API_KEY=your-claude-key
ANTHROPIC_BASE_URL=https://api.anthropic.com  # 可选
```

重启服务即可生效。

### Q3: 可以同时使用多个代理吗？

可以！不同服务可以使用不同的配置：

```bash
# LLM 使用国内代理
OPENAI_API_KEY=sk-proxy-key
OPENAI_BASE_URL=https://china-proxy.com/v1

# Embedding 使用官方 API（如果访问更稳定）
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002
# 不设置 OPENAI_BASE_URL，Embedding 会使用官方 API
```

---

## 自建代理示例

### Nginx 反向代理配置

```nginx
server {
    listen 443 ssl;
    server_name your-proxy.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /v1/ {
        proxy_pass https://api.openai.com/v1/;
        proxy_set_header Host api.openai.com;
        proxy_set_header Authorization $http_authorization;
        proxy_ssl_server_name on;
    }
}
```

### Cloudflare Worker 代理

```javascript
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url)
  url.host = 'api.openai.com'
  
  return fetch(url, {
    method: request.method,
    headers: request.headers,
    body: request.body
  })
}
```

---

## 性能优化建议

1. **选择就近的代理服务器** - 延迟更低
2. **使用缓存** - FinnewsHunter 已集成 Redis 缓存
3. **调整超时设置** - 如果代理较慢，可增加超时时间：
   ```bash
   CRAWLER_TIMEOUT=60  # 增加到 60 秒
   ```

---

## 安全建议

⚠️ **重要提示**:
1. **不要在代码中硬编码 API Key**
2. **不要将 `.env` 文件提交到 Git**
3. **定期轮换 API Key**
4. **使用 HTTPS 代理服务**
5. **限制 API Key 权限**

---

**需要帮助？** 查看 [README.md](../README.md) 或提交 Issue。

