#!/usr/bin/env python3
"""
检查新闻的向量化状态
"""
import sys
import os
import asyncio

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select, func
from app.core.database import get_db
from app.models.news import News
from app.models.analysis import Analysis

async def main():
    try:
        async for db in get_db():
            # 统计总体情况
            total_result = await db.execute(select(func.count(News.id)))
            total_news = total_result.scalar() or 0
            
            embedded_result = await db.execute(
                select(func.count(News.id)).where(News.is_embedded == 1)
            )
            embedded_count = embedded_result.scalar() or 0
            
            analyzed_result = await db.execute(
                select(func.count(News.id)).where(News.sentiment_score.isnot(None))
            )
            analyzed_count = analyzed_result.scalar() or 0
            
            # 查找已分析但未向量化的新闻
            not_embedded_result = await db.execute(
                select(News.id, News.title, News.sentiment_score)
                .where(
                    News.sentiment_score.isnot(None),
                    News.is_embedded == 0
                )
                .order_by(News.id.desc())
                .limit(10)
            )
            not_embedded_news = not_embedded_result.all()
            
            print("=" * 60)
            print("新闻向量化状态统计")
            print("=" * 60)
            print(f"\n📊 总体统计:")
            print(f"  总新闻数: {total_news}")
            print(f"  已分析新闻: {analyzed_count}")
            print(f"  已向量化新闻: {embedded_count}")
            print(f"  已分析但未向量化: {analyzed_count - embedded_count}")
            
            if not_embedded_news:
                print(f"\n⚠️  最近10条已分析但未向量化的新闻:")
                for news_id, title, sentiment_score in not_embedded_news:
                    title_preview = title[:50] + "..." if len(title) > 50 else title
                    print(f"  - ID: {news_id}, 情感分数: {sentiment_score:.2f}")
                    print(f"    标题: {title_preview}")
            else:
                print("\n✅ 所有已分析的新闻都已向量化")
            
            print("\n" + "=" * 60)
            print("💡 可能的原因:")
            print("  1. Embedding API 超时（20秒超时）")
            print("  2. Milvus 连接失败")
            print("  3. Embedding 服务配置错误")
            print("\n🔧 解决方案:")
            print("  1. 检查后端日志中的 embedding 错误")
            print("  2. 确认 Milvus 服务正在运行")
            print("  3. 检查 embedding API 配置（百炼/OpenAI）")
            print("  4. 可以手动重新向量化这些新闻")
            print("=" * 60)
            
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
