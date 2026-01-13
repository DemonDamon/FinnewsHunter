#!/usr/bin/env python3
"""
检查 Milvus 向量存储中的数据
"""
import sys
import os
import asyncio

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.storage.vector_storage import get_vector_storage
from app.core.config import settings

def main():
    try:
        print("=" * 60)
        print("Milvus 向量存储信息")
        print("=" * 60)
        
        storage = get_vector_storage()
        stats = storage.get_stats()
        
        print(f"\n📊 集合统计信息:")
        print(f"  集合名称: {stats['collection_name']}")
        print(f"  向量维度: {stats['dim']}")
        num_entities = stats['num_entities']
        if isinstance(num_entities, str):
            print(f"  存储的向量数量: {num_entities}")
        else:
            print(f"  存储的向量数量: {num_entities}")
            if num_entities == 0:
                print(f"  ⚠️  注意：如果显示为 0，可能是 flush 失败导致统计不准确")
        print(f"  Milvus地址: {storage.host}:{storage.port}")
        
        # 查询一些示例数据
        print(f"\n📝 查询示例数据:")
        try:
            # 使用 agenticx 的 query 方法获取数据
            from agenticx.storage.vectordb_storages.base import VectorDBQuery
            
            # 创建一个零向量查询来获取所有数据（top_k 限制结果数）
            zero_vector = [0.0] * stats['dim']
            query = VectorDBQuery(query_vector=zero_vector, top_k=10)
            
            # query 是同步方法，可以直接调用
            results = storage.milvus_storage.query(query)
            
            if results:
                print(f"   ✅ 找到 {len(results)} 条记录")
                if isinstance(stats['num_entities'], str) or stats['num_entities'] != len(results):
                    print(f"   ℹ️  统计数量: {stats['num_entities']}")
                print()
                for i, result in enumerate(results[:5], 1):  # 只显示前5条
                    payload = result.record.payload or {}
                    news_id = payload.get('news_id', result.record.id)
                    text = payload.get('text', '')
                    text_preview = text[:100] + "..." if len(text) > 100 else text
                    print(f"  {i}. 新闻ID: {news_id}")
                    print(f"     文本预览: {text_preview}")
                if len(results) > 5:
                    print(f"\n  ... 还有 {len(results) - 5} 条记录未显示")
            else:
                if stats['num_entities'] == 0:
                    print("   ⚠️  未找到数据，集合可能确实为空")
                    print("   提示: 向量数据会在新闻分析时自动生成并存储")
                else:
                    print(f"   ⚠️  未找到数据，但统计显示有 {stats['num_entities']} 条记录")
                    print("   可能的原因：数据在缓冲区中，需要等待 Milvus 自动刷新")
        except Exception as e:
            print(f"  ❌ 无法查询数据: {e}")
            import traceback
            traceback.print_exc()
            if stats['num_entities'] == 0:
                print("\n   提示: 如果这是首次运行，集合可能确实为空")
        
        print("\n" + "=" * 60)
        print("💡 提示:")
        print("  - 向量数据存储在 Milvus 数据库中")
        print("  - 可以通过 Milvus 客户端工具查看完整数据")
        print("  - 向量维度必须与 embedding 模型匹配")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print("\n可能的原因:")
        print("  1. Milvus 服务未启动")
        print("  2. Milvus 连接配置错误")
        print("  3. 集合尚未创建")
        print("\n检查方法:")
        print(f"  - 确认 Milvus 运行在 {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
        print(f"  - 检查 .env 文件中的 MILVUS_* 配置")

if __name__ == "__main__":
    main()
