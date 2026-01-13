# FinnewsHunter Backend

Backend service for the financial news intelligent analysis system based on the AgenticX framework.

## Documentation Navigation

### Quick Start
- **[QUICKSTART.md](../QUICKSTART.md)** - Quick start guide (recommended for beginners)

### Configuration Guides
- **[CONFIG_GUIDE.md](CONFIG_GUIDE.md)** - **Unified Configuration Guide** (recommended)
  - Single configuration file supports all LLM providers
  - Quick switching between OpenAI / Bailian / Proxy
  - Includes scenario examples and working principles
  
- **[env.example](env.example)** - Configuration template (with comments for all scenarios)

### Specialized Configuration
- **[BAILIAN_SETUP.md](BAILIAN_SETUP.md)** - Detailed Alibaba Cloud Bailian configuration (recommended for Chinese users)
- **[API_PROXY_GUIDE.md](API_PROXY_GUIDE.md)** - API proxy configuration guide

---

## Quick Configuration

### Method 1: Interactive Script (Recommended)

```bash
chmod +x setup_env.sh
./setup_env.sh

# Follow the prompts to select:
# 1) OpenAI Official
# 2) Alibaba Cloud Bailian (recommended for Chinese users)
# 3) Other Proxy
# 4) Manual Configuration
```

### Method 2: Manual Configuration

```bash
cp env.example .env
nano .env  # Choose configuration scheme according to comments
```

---

## Main Features

- **Multi-Agent System**: Based on AgenticX framework
  - NewsAnalyst: News analysis agent
  - More agents under development...

- **Data Collection**:
  - Sina Finance crawler
  - JRJ Finance crawler

- **Storage System**:
  - PostgreSQL: Relational data storage
  - Milvus: Vector database
  - Redis: Cache and task queue

- **LLM Support**:
  - OpenAI (GPT-3.5/GPT-4)
  - Alibaba Cloud Bailian (Qwen)
  - Other OpenAI-compatible services

---

## Project Structure

```
backend/
├── app/
│   ├── agents/          # Agent definitions
│   ├── api/             # FastAPI routes
│   ├── core/            # Core configuration
│   ├── models/          # Data models
│   ├── services/        # Business services
│   ├── storage/         # Storage wrappers
│   └── tools/           # Crawlers and tools
├── logs/                # Log files
├── tests/               # Test files
├── .env                 # Environment configuration (copy from env.example)
├── env.example          # Configuration template
├── requirements.txt     # Python dependencies
└── start.sh            # Startup script
```

---

## Development Guide

### Start Development Environment

```bash
# 1. Configure environment variables
./setup_env.sh

# 2. Start services (including Docker containers)
./start.sh
```

### Utility Scripts

The project provides some utility scripts located in the `tests/` directory:

```bash
# Check Milvus vector storage data
python tests/check_milvus_data.py

# Check news embedding status
python tests/check_news_embedding_status.py

# Manually vectorize a specific news item (for fixing unvectorized news)
python tests/manual_vectorize.py <news_id>
```

### View Logs

```bash
tail -f logs/finnews.log
```

---

## Common Configuration Scenarios

### OpenAI Official
```bash
LLM_MODEL=gpt-3.5-turbo
OPENAI_API_KEY=sk-openai-key
MILVUS_DIM=1536
```

### Alibaba Cloud Bailian (Recommended for Chinese Users)
```bash
LLM_MODEL=qwen-plus
OPENAI_API_KEY=sk-bailian-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MILVUS_DIM=1024
```

### OpenAI Proxy
```bash
LLM_MODEL=gpt-3.5-turbo
OPENAI_API_KEY=sk-proxy-key
OPENAI_BASE_URL=https://your-proxy.com/v1
MILVUS_DIM=1536
```

For detailed information, see **[CONFIG_GUIDE.md](CONFIG_GUIDE.md)**

---

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Troubleshooting

If the documentation page appears blank or keeps loading:

1. **Check Browser Console**: Press F12 to open developer tools, check Console and Network tabs for errors
2. **Try ReDoc**: If Swagger UI fails to load, try accessing ReDoc (uses a different CDN)
3. **Clear Browser Cache**: Press `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac) to force refresh
4. **Check Network Connection**: Documentation pages need to load JavaScript resources from CDN, ensure network connection is normal
5. **Check Backend Service**: Ensure the backend service is running, verify by accessing http://localhost:8000/health
