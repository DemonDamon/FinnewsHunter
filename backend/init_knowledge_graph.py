#!/usr/bin/env python
"""
初始化知识图谱
创建 Neo4j 约束、索引，并为示例股票构建图谱
"""
import asyncio
import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def init_knowledge_graph():
    """初始化知识图谱"""
    try:
        from app.core.neo4j_client import get_neo4j_client
        from app.knowledge.graph_service import get_graph_service
        from app.knowledge.knowledge_extractor import (
            create_knowledge_extractor,
            AkshareKnowledgeExtractor
        )
        
        logger.info("=" * 80)
        logger.info("开始初始化知识图谱")
        logger.info("=" * 80)
        
        # 1. 测试 Neo4j 连接
        logger.info("\n[1/4] 测试 Neo4j 连接...")
        neo4j_client = get_neo4j_client()
        if neo4j_client.health_check():
            logger.info("✅ Neo4j 连接正常")
        else:
            logger.error("❌ Neo4j 连接失败，请检查配置")
            sys.exit(1)
        
        # 2. 初始化约束和索引
        logger.info("\n[2/4] 初始化数据库约束和索引...")
        graph_service = get_graph_service()
        logger.info("✅ 约束和索引已创建")
        
        # 3. 为示例股票创建图谱
        logger.info("\n[3/4] 为示例股票创建知识图谱...")
        
        example_stocks = [
            ("SH600519", "贵州茅台"),  # 示例1：大盘蓝筹
            ("SZ300634", "彩讯股份"),  # 示例2：中小板
        ]
        
        extractor = create_knowledge_extractor()
        
        for stock_code, stock_name in example_stocks:
            logger.info(f"\n处理: {stock_name}({stock_code})")
            
            # 检查是否已存在
            existing = graph_service.get_company_graph(stock_code)
            if existing:
                logger.info(f"  ℹ️ 图谱已存在，跳过")
                continue
            
            # 从 akshare 获取信息
            logger.info(f"  🔍 从 akshare 获取信息...")
            akshare_info = AkshareKnowledgeExtractor.extract_company_info(stock_code)
            
            if not akshare_info:
                logger.warning(f"  ⚠️ akshare 未返回数据，跳过")
                continue
            
            # 使用 LLM 提取详细信息
            logger.info(f"  🧠 使用 LLM 提取详细信息...")
            base_graph = await extractor.extract_from_akshare(
                stock_code, stock_name, akshare_info
            )
            
            # 构建图谱
            logger.info(f"  💾 构建图谱...")
            success = graph_service.build_company_graph(base_graph)
            
            if success:
                stats = graph_service.get_graph_stats(stock_code)
                logger.info(f"  ✅ 图谱构建成功: {stats}")
            else:
                logger.error(f"  ❌ 图谱构建失败")
        
        # 4. 显示统计信息
        logger.info("\n[4/4] 图谱统计...")
        companies = graph_service.list_all_companies()
        logger.info(f"✅ 当前共有 {len(companies)} 家公司的知识图谱")
        
        for company in companies:
            stats = graph_service.get_graph_stats(company['stock_code'])
            logger.info(f"  - {company['stock_name']}({company['stock_code']}): {stats}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✨ 知识图谱初始化完成！")
        logger.info("=" * 80)
        logger.info("\n下一步：")
        logger.info("  1. 访问 http://localhost:7474 查看 Neo4j 浏览器")
        logger.info("  2. 用户名: neo4j, 密码: finnews_neo4j_password")
        logger.info("  3. 执行定向爬取时，系统会自动使用知识图谱进行多关键词并发检索")
        logger.info("\n")
        
    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(init_knowledge_graph())

