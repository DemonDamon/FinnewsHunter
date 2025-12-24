"""
搜索引擎爬虫工具
直接爬取搜索引擎结果页面（Bing/Baidu）
"""
import logging
import re
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import time

logger = logging.getLogger(__name__)


class SearchEngineCrawler:
    """
    搜索引擎爬虫
    直接爬取 Bing/Baidu 搜索结果
    """
    
    def __init__(self):
        """初始化搜索引擎爬虫"""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        logger.info("🔧 搜索引擎爬虫已初始化")
    
    def _fetch_url(self, url: str, timeout: int = 10) -> Optional[str]:
        """
        爬取URL内容
        
        Args:
            url: 目标URL
            timeout: 超时时间
            
        Returns:
            HTML内容
        """
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            # 尝试检测编码
            if response.encoding == 'ISO-8859-1':
                # 对于中文网站，尝试使用 gb2312 或 utf-8
                encodings = ['utf-8', 'gb2312', 'gbk']
                for enc in encodings:
                    try:
                        response.encoding = enc
                        _ = response.text
                        break
                    except:
                        continue
            
            return response.text
            
        except Exception as e:
            logger.error(f"❌ 爬取失败 {url}: {e}")
            return None
    
    def search_with_engine(
        self,
        query: str,
        engine: str = "bing",
        days: int = 30,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        使用搜索引擎搜索新闻
        
        Args:
            query: 搜索关键词
            engine: 搜索引擎 (bing/baidu)
            days: 时间范围（天）
            max_results: 最大结果数
            
        Returns:
            新闻列表
        """
        if engine not in self.search_engines:
            logger.error(f"❌ 不支持的搜索引擎: {engine}")
            return []
        
        # 构建搜索URL
        search_query = self._build_search_query(query, days)
        search_url = self.search_engines[engine].format(query=quote_plus(search_query))
        
        logger.info(f"🔍 搜索引擎爬取: {engine} - {search_query}")
        logger.info(f"    URL: {search_url}")
        
        # 创建临时输出目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # 爬取搜索结果页面
            result = self._call_mcp_crawl(search_url, temp_dir)
            
            if not result:
                logger.warning(f"⚠️ 搜索引擎爬取失败: {search_url}")
                return []
            
            # 解析搜索结果
            news_items = self._parse_search_results(
                content=result.get("content", ""),
                engine=engine,
                max_results=max_results
            )
            
            logger.info(f"✅ 从 {engine} 提取到 {len(news_items)} 条结果")
            return news_items
    
    def _build_search_query(self, query: str, days: int) -> str:
        """
        构建搜索查询字符串（添加时间限制）
        
        Args:
            query: 原始查询
            days: 时间范围
            
        Returns:
            增强的搜索查询
        """
        # 添加时间范围（对于 Bing 和 Baidu）
        # Bing: 支持 "query site:xxx.com"
        # 可以添加新闻源限制
        
        # 可选：限制到新闻网站
        news_sites = [
            "sina.com.cn",
            "163.com",
            "eastmoney.com",
            "cnstock.com",
            "stcn.com",
            "caijing.com.cn",
            "yicai.com",
        ]
        
        # 构建基础查询
        enhanced_query = f"{query} 新闻"
        
        # 添加时间提示词
        if days <= 7:
            enhanced_query += " 最近一周"
        elif days <= 30:
            enhanced_query += " 最近一个月"
        
        return enhanced_query
    
    def _parse_search_results(
        self,
        content: str,
        engine: str,
        max_results: int
    ) -> List[Dict[str, Any]]:
        """
        解析搜索引擎返回的内容，提取新闻链接和标题
        
        Args:
            content: 爬取的页面内容（Markdown格式）
            engine: 搜索引擎类型
            max_results: 最大结果数
            
        Returns:
            新闻条目列表
        """
        news_items = []
        
        # 从 Markdown 内容中提取链接
        # 格式：[标题](URL)
        link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
        matches = re.findall(link_pattern, content)
        
        for title, url in matches[:max_results]:
            # 过滤掉搜索引擎自身的链接
            if engine in url.lower():
                continue
            
            # 过滤掉非新闻链接
            if not self._is_news_url(url):
                continue
            
            news_items.append({
                "title": title.strip(),
                "url": url.strip(),
                "snippet": "",  # 暂时为空，后续可以从 content 中提取
                "source": self._extract_source_from_url(url),
                "engine": engine
            })
        
        return news_items
    
    def _is_news_url(self, url: str) -> bool:
        """判断是否为新闻URL"""
        news_domains = [
            "sina.com", "163.com", "eastmoney.com", "cnstock.com",
            "stcn.com", "caijing.com", "yicai.com", "nbd.com",
            "jwview.com", "eeo.com.cn", "finance.qq.com"
        ]
        return any(domain in url.lower() for domain in news_domains)
    
    def _extract_source_from_url(self, url: str) -> str:
        """从URL提取来源"""
        domain_mapping = {
            "sina.com": "新浪财经",
            "163.com": "网易财经",
            "eastmoney.com": "东方财富",
            "cnstock.com": "中国证券网",
            "stcn.com": "证券时报",
            "caijing.com": "财经网",
            "yicai.com": "第一财经",
            "nbd.com": "每日经济新闻",
            "jwview.com": "金融界",
            "eeo.com.cn": "经济观察网",
            "qq.com": "腾讯财经",
        }
        
        for domain, source in domain_mapping.items():
            if domain in url.lower():
                return source
        
        return "未知来源"
    
    def search_stock_news(
        self,
        stock_name: str,
        stock_code: str,
        days: int = 30,
        engines: Optional[List[str]] = None,
        max_per_engine: int = 30
    ) -> List[Dict[str, Any]]:
        """
        搜索股票新闻（多搜索引擎）
        
        Args:
            stock_name: 股票名称
            stock_code: 股票代码
            days: 时间范围
            engines: 搜索引擎列表，默认 ["bing"]
            max_per_engine: 每个搜索引擎最大结果数
            
        Returns:
            新闻列表
        """
        if engines is None:
            engines = ["bing"]  # 默认只用 Bing（Baidu 可能需要处理反爬）
        
        all_news = []
        
        # 构建搜索关键词
        queries = [
            stock_name,
            f"{stock_name} {stock_code}",
            f"{stock_name} 公告",
        ]
        
        for engine in engines:
            for query in queries:
                try:
                    news = self.search_with_engine(
                        query=query,
                        engine=engine,
                        days=days,
                        max_results=max_per_engine
                    )
                    all_news.extend(news)
                except Exception as e:
                    logger.error(f"❌ 搜索失败 [{engine}] {query}: {e}")
        
        # 去重（按URL）
        seen_urls = set()
        unique_news = []
        for news in all_news:
            url = news.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_news.append(news)
        
        logger.info(f"✅ 多引擎搜索完成: 总计 {len(unique_news)} 条（去重后）")
        return unique_news


# 便捷函数
def create_search_engine_crawler(mcp_server_path: Optional[str] = None) -> SearchEngineCrawler:
    """创建搜索引擎爬虫实例"""
    return SearchEngineCrawler(mcp_server_path)


# 测试代码
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    crawler = create_search_engine_crawler()
    
    # 测试搜索
    results = crawler.search_stock_news(
        stock_name="深振业A",
        stock_code="000006",
        days=7,
        engines=["bing"],
        max_per_engine=10
    )
    
    print(f"\n✅ 搜索到 {len(results)} 条新闻:")
    for i, news in enumerate(results[:5], 1):
        print(f"{i}. {news['title']}")
        print(f"   来源: {news['source']}")
        print(f"   URL: {news['url']}")

