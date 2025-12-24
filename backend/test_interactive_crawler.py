"""
交互式爬虫测试脚本
用于测试 BasicWebCrawler 集成功能
"""
import sys
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入交互式爬虫
try:
    from app.tools.interactive_crawler import create_interactive_crawler, search_and_crawl
    logger.info("✅ 成功导入交互式爬虫")
except ImportError as e:
    logger.error(f"❌ 导入失败: {e}")
    sys.exit(1)


def test_basic_search():
    """测试基础搜索"""
    logger.info("\n" + "="*60)
    logger.info("测试 1: 基础 Bing 搜索")
    logger.info("="*60)
    
    crawler = create_interactive_crawler(headless=True)
    
    query = "深振业Ａ 房地产"
    logger.info(f"搜索关键词: {query}")
    
    results = crawler.interactive_search(
        query,
        engines=["bing"],
        num_results=10
    )
    
    logger.info(f"\n获得 {len(results)} 条搜索结果:")
    for i, r in enumerate(results[:5], 1):
        logger.info(f"  {i}. {r['title'][:50]}...")
        logger.info(f"     URL: {r['url']}")
        logger.info(f"     来源: {r.get('source', 'unknown')}\n")
    
    return results


def test_search_and_crawl():
    """测试搜索和爬取"""
    logger.info("\n" + "="*60)
    logger.info("测试 2: 搜索并爬取页面")
    logger.info("="*60)
    
    query = "精密温控节能设备"
    logger.info(f"搜索关键词: {query}")
    
    result = search_and_crawl(
        query,
        engines=["bing"],
        max_search_results=10,
        max_crawl_results=3,
        headless=True
    )
    
    logger.info(f"\n搜索结果: {len(result['search_results'])} 条")
    logger.info(f"爬取成功: {len(result['crawled_results'])} 个页面")
    
    for i, page in enumerate(result['crawled_results'][:2], 1):
        logger.info(f"\n  爬取结果 {i}:")
        logger.info(f"    标题: {page['title']}")
        logger.info(f"    URL: {page['url']}")
        logger.info(f"    内容长度: {len(page['content'])} 字符")
    
    return result


def test_baidu_search():
    """测试百度搜索"""
    logger.info("\n" + "="*60)
    logger.info("测试 3: 百度搜索（可选）")
    logger.info("="*60)
    
    crawler = create_interactive_crawler(headless=True)
    
    query = "机房环境控制系统"
    logger.info(f"搜索关键词: {query}")
    
    try:
        results = crawler.search_on_baidu(
            query,
            num_results=5
        )
        
        logger.info(f"\n获得 {len(results)} 条百度搜索结果:")
        for i, r in enumerate(results[:3], 1):
            logger.info(f"  {i}. {r['title'][:50]}...")
            logger.info(f"     URL: {r['url']}\n")
        
        return results
    except Exception as e:
        logger.warning(f"⚠️ 百度搜索失败（可能被反爬）: {e}")
        return []


def test_interactive_search():
    """测试多引擎搜索"""
    logger.info("\n" + "="*60)
    logger.info("测试 4: 多引擎交互式搜索")
    logger.info("="*60)
    
    crawler = create_interactive_crawler(headless=True)
    
    query = "*ST国华"
    logger.info(f"搜索关键词: {query}")
    
    results = crawler.interactive_search(
        query,
        engines=["bing"],  # 仅用 Bing（Baidu 可能被反爬）
        num_results=8
    )
    
    logger.info(f"\n综合搜索结果: {len(results)} 条")
    for i, r in enumerate(results[:3], 1):
        logger.info(f"  {i}. [{r.get('source', 'web')}] {r['title'][:50]}...")
    
    return results


def main():
    """运行所有测试"""
    logger.info("🚀 开始交互式爬虫测试\n")
    
    try:
        # 测试 1: 基础搜索
        test_basic_search()
        
        # 测试 2: 搜索和爬取
        test_search_and_crawl()
        
        # 测试 3: 百度搜索（可选）
        # test_baidu_search()
        
        # 测试 4: 多引擎搜索
        # test_interactive_search()
        
        logger.info("\n" + "="*60)
        logger.info("✅ 所有测试完成！")
        logger.info("="*60)
        
    except KeyboardInterrupt:
        logger.info("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        logger.error(f"\n\n❌ 测试失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

