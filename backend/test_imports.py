#!/usr/bin/env python
"""
测试所有模块导入是否正常
"""
import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing imports...")
print("-" * 60)

try:
    print("✓ Testing core.config...")
    from app.core.config import settings
    print(f"  - App: {settings.APP_NAME} v{settings.APP_VERSION}")
    
    print("✓ Testing models...")
    from app.models import News, Stock, Analysis
    print(f"  - Models: News, Stock, Analysis")
    
    print("✓ Testing tools...")
    from app.tools import SinaCrawlerTool, TextCleanerTool
    print(f"  - Tools: SinaCrawlerTool, TextCleanerTool")
    
    print("✓ Testing services...")
    from app.services import LLMService, EmbeddingService, AnalysisService
    print(f"  - Services: LLMService, EmbeddingService, AnalysisService")
    
    print("✓ Testing agents...")
    from app.agents import NewsAnalystAgent
    print(f"  - Agents: NewsAnalystAgent")
    
    print("✓ Testing API routes...")
    from app.api.v1 import api_router
    print(f"  - API Router loaded")
    
    print("✓ Testing main app...")
    from app.main import app
    print(f"  - FastAPI app loaded")
    
    print("-" * 60)
    print("✅ All imports successful!")
    sys.exit(0)
    
except Exception as e:
    print("-" * 60)
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

