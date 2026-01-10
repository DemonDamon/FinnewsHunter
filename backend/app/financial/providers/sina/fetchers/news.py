"""
新浪财经新闻 Fetcher

从 tools/sina_crawler.py 迁移而来，适配 TET Pipeline 架构。

主要变更:
- transform_query: 将 NewsQueryParams 转换为爬虫参数
- extract_data: 执行网页爬取
- transform_data: 将原始数据转换为 NewsData 标准模型

保留原有的:
- 网页解析逻辑
- 标题/内容/日期提取
- 股票代码提取
- 噪音过滤

来源: tools/sina_crawler.py (SinaCrawlerTool)
"""
import re
import time
import hashlib
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from bs4 import BeautifulSoup

from ...base import BaseFetcher
from ....models.news import NewsQueryParams, NewsData

logger = logging.getLogger(__name__)


class SinaNewsFetcher(BaseFetcher[NewsQueryParams, NewsData]):
    """
    新浪财经新闻获取器

    实现 TET Pipeline:
    - Transform Query: 将 NewsQueryParams 转换为爬虫参数
    - Extract Data: 爬取网页
    - Transform Data: 解析为 NewsData
    """

    query_model = NewsQueryParams
    data_model = NewsData

    # 新浪财经最新滚动新闻页面
    BASE_URL = "https://finance.sina.com.cn/roll/c/56592.shtml"
    SOURCE_NAME = "sina"

    # 请求配置
    DEFAULT_TIMEOUT = 30
    DEFAULT_DELAY = 0.5
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # 噪音文本模式
    NOISE_PATTERNS = [
        r'^责任编辑', r'^编辑[:：]', r'^来源[:：]', r'^声明[:：]',
        r'^免责声明', r'^版权', r'^copyright', r'^点击进入',
        r'^相关阅读', r'^延伸阅读', r'登录新浪财经APP',
        r'搜索【信披】', r'缩小字体', r'放大字体', r'收藏',
        r'微博', r'微信', r'分享', r'腾讯QQ',
    ]

    def __init__(self):
        super().__init__()
        self._session = None

    def _get_session(self):
        """获取 requests Session (延迟初始化)"""
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': self.DEFAULT_USER_AGENT
            })
        return self._session

    def transform_query(self, params: NewsQueryParams) -> Dict[str, Any]:
        """
        将标准参数转换为爬虫参数

        Args:
            params: 标准查询参数

        Returns:
            爬虫参数字典
        """
        query = {
            "base_url": self.BASE_URL,
            "limit": params.limit,
            "stock_codes": params.stock_codes or [],
            "keywords": params.keywords or [],
        }

        # 如果有股票代码，构建股票新闻 URL
        if params.stock_codes:
            query["stock_urls"] = []
            for code in params.stock_codes:
                symbol = self._normalize_symbol(code)
                stock_url = (
                    f"https://vip.stock.finance.sina.com.cn"
                    f"/corp/go.php/vCB_AllNewsStock/symbol/{symbol}.phtml"
                )
                query["stock_urls"].append(stock_url)

        return query

    async def extract_data(self, query: Dict[str, Any]) -> List[Dict]:
        """
        执行网页爬取

        Args:
            query: transform_query 返回的参数

        Returns:
            原始新闻数据列表
        """
        all_news = []
        limit = query["limit"]

        # 确定要爬取的 URL 列表
        urls_to_crawl = query.get("stock_urls", [query["base_url"]])
        if not urls_to_crawl:
            urls_to_crawl = [query["base_url"]]

        for url in urls_to_crawl:
            try:
                news_items = await self._crawl_page(url, limit - len(all_news))
                all_news.extend(news_items)

                if len(all_news) >= limit:
                    break

            except Exception as e:
                self.logger.error(f"Failed to crawl {url}: {e}")
                continue

        return all_news[:limit]

    async def _crawl_page(self, url: str, max_items: int) -> List[Dict]:
        """爬取单个页面"""
        import asyncio

        self.logger.info(f"Fetching page: {url}")

        # 使用 run_in_executor 执行同步请求
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._fetch_page_sync(url)
        )

        if not response:
            return []

        # 设置编码
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'lxml')

        # 查找新闻链接
        news_links = self._extract_news_links(soup)
        self.logger.info(f"Found {len(news_links)} news links")

        # 爬取每条新闻详情
        news_list = []
        for idx, news_url in enumerate(news_links[:max_items], 1):
            try:
                self.logger.debug(f"Crawling news {idx}/{min(len(news_links), max_items)}")
                news_item = await self._crawl_news_detail(news_url)
                if news_item:
                    news_list.append(news_item)
            except Exception as e:
                self.logger.warning(f"Failed to crawl {news_url}: {e}")
                continue

            # 请求间隔
            await asyncio.sleep(self.DEFAULT_DELAY)

        return news_list

    def _fetch_page_sync(self, url: str):
        """同步获取页面"""
        try:
            session = self._get_session()
            response = session.get(url, timeout=self.DEFAULT_TIMEOUT)
            response.raise_for_status()
            return response
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _extract_news_links(self, soup: BeautifulSoup) -> List[str]:
        """提取新闻链接"""
        news_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            # 匹配新浪财经新闻 URL
            if 'finance.sina.com.cn' in href and ('/stock/' in href or '/roll/' in href):
                if href.startswith('http'):
                    news_links.append(href)
                elif href.startswith('//'):
                    news_links.append('http:' + href)

        # 去重
        return list(set(news_links))

    async def _crawl_news_detail(self, url: str) -> Optional[Dict]:
        """爬取新闻详情"""
        import asyncio

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._fetch_page_sync(url)
        )

        if not response:
            return None

        try:
            soup = BeautifulSoup(response.content, "lxml")
            raw_html = response.text

            # 提取各字段
            title = self._extract_title(soup)
            if not title:
                return None

            summary, keywords = self._extract_meta(soup)
            publish_time = self._extract_date(soup)
            stock_codes = self._extract_stock_codes(soup)
            content = self._extract_content(soup)

            if not content or len(content) < 50:
                return None

            return {
                "url": url,
                "title": title,
                "content": content,
                "summary": summary,
                "keywords": keywords,
                "publish_time": publish_time,
                "stock_codes": stock_codes,
                "raw_html": raw_html,
            }

        except Exception as e:
            self.logger.error(f"Error parsing {url}: {e}")
            return None

    def transform_data(
        self,
        raw_data: List[Dict],
        query: NewsQueryParams
    ) -> List[NewsData]:
        """
        将原始数据转换为 NewsData 标准模型

        Args:
            raw_data: extract_data 返回的原始数据
            query: 原始查询参数

        Returns:
            NewsData 列表
        """
        results = []
        for item in raw_data:
            try:
                news = NewsData(
                    id=NewsData.generate_id(item["url"]),
                    title=item["title"],
                    content=item["content"],
                    summary=item.get("summary"),
                    source=self.SOURCE_NAME,
                    source_url=item["url"],
                    publish_time=item.get("publish_time") or datetime.now(),
                    stock_codes=item.get("stock_codes", []),
                    keywords=item.get("keywords", []),
                    extra={"raw_html": item.get("raw_html")},
                )
                results.append(news)
            except Exception as e:
                self.logger.warning(f"Failed to transform item: {e}")
                continue

        return results

    # ========== 辅助方法（从原 sina_crawler.py 迁移）==========

    def _normalize_symbol(self, code: str) -> str:
        """标准化股票代码为新浪格式"""
        code = code.upper().replace("SH", "sh").replace("SZ", "sz")
        if code.isdigit():
            if code.startswith("6"):
                return f"sh{code}"
            else:
                return f"sz{code}"
        return code.lower()

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """提取标题"""
        title_tag = soup.find('h1', class_='main-title')
        if not title_tag:
            title_tag = soup.find('h1')
        if not title_tag:
            title_tag = soup.find('title')

        if title_tag:
            title = title_tag.get_text().strip()
            title = re.sub(r'[-_].*?(新浪|财经|网)', '', title)
            return title.strip()
        return None

    def _extract_meta(self, soup: BeautifulSoup) -> tuple:
        """提取元数据（摘要和关键词）"""
        summary = ""
        keywords = []

        for meta in soup.find_all('meta'):
            name = meta.get('name', '').lower()
            content = meta.get('content', '')

            if name == 'description':
                summary = content
            elif name == 'keywords':
                keywords = [kw.strip() for kw in content.split(',') if kw.strip()]

        return summary, keywords

    def _extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """提取发布时间"""
        for span in soup.find_all('span'):
            class_attr = span.get('class', [])
            if 'date' in class_attr or 'time-source' in class_attr:
                date_text = span.get_text()
                return self._parse_date(date_text)

            if span.get('id') == 'pub_date':
                date_text = span.get_text()
                return self._parse_date(date_text)

        return None

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """解析日期字符串"""
        try:
            date_text = date_text.strip()
            date_text = date_text.replace('年', '-').replace('月', '-').replace('日', '')

            for fmt in ['%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    return datetime.strptime(date_text.strip(), fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    def _extract_stock_codes(self, soup: BeautifulSoup) -> List[str]:
        """提取关联股票代码"""
        stock_codes = []
        for span in soup.find_all('span'):
            span_id = span.get('id', '')
            if span_id.startswith('stock_'):
                code = span_id[6:].upper()
                if code:
                    stock_codes.append(code)
        return list(set(stock_codes))

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取正文内容"""
        content_selectors = [
            {'id': 'artibody'},
            {'class': 'article-content'},
            {'class': 'article'},
            {'id': 'article'},
        ]

        for selector in content_selectors:
            content_div = soup.find(['div', 'article'], selector)
            if content_div:
                # 移除噪音元素
                for tag in content_div.find_all([
                    'script', 'style', 'iframe', 'ins',
                    'select', 'input', 'button', 'form'
                ]):
                    tag.decompose()

                for ad in content_div.find_all(class_=re.compile(
                    r'ad|banner|share|otherContent|recommend|app-guide', re.I
                )):
                    ad.decompose()

                # 提取文本
                full_text = content_div.get_text(separator='\n', strip=True)
                lines = full_text.split('\n')
                article_parts = []

                for line in lines:
                    line = line.strip()
                    if not line or len(line) < 2:
                        continue

                    if not self._is_noise_text(line):
                        article_parts.append(line)

                if article_parts:
                    return '\n'.join(article_parts)

        return ""

    def _is_noise_text(self, text: str) -> bool:
        """判断是否为噪音文本"""
        text_lower = text.lower().strip()
        for pattern in self.NOISE_PATTERNS:
            if re.match(pattern, text_lower, re.I) or re.search(pattern, text_lower, re.I):
                return True
        return False

    def _extract_chinese_ratio(self, text: str) -> float:
        """计算中文字符比例"""
        pattern = re.compile(r'[\u4e00-\u9fa5]+')
        chinese_chars = pattern.findall(text)
        chinese_count = sum(len(chars) for chars in chinese_chars)
        total_count = len(text)
        return chinese_count / total_count if total_count > 0 else 0
