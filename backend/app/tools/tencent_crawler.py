"""
腾讯财经爬虫工具
目标URL: https://news.qq.com/ch/finance/
"""
import re
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import json

from .crawler_base import BaseCrawler, NewsItem

logger = logging.getLogger(__name__)


class TencentCrawlerTool(BaseCrawler):
    """
    腾讯财经新闻爬虫
    爬取腾讯财经频道最新新闻
    """
    
    BASE_URL = "https://news.qq.com/ch/finance_stock/"
    # 腾讯新闻API（如果页面动态加载，可能需要调用API）
    API_URL = "https://pacaio.match.qq.com/irs/rcd"
    SOURCE_NAME = "tencent"
    
    def __init__(self):
        super().__init__(
            name="tencent_finance_crawler",
            description="Crawl financial news from Tencent Finance (news.qq.com)"
        )
    
    def crawl(self, start_page: int = 1, end_page: int = 1) -> List[NewsItem]:
        """
        爬取腾讯财经新闻
        
        Args:
            start_page: 起始页码
            end_page: 结束页码
            
        Returns:
            新闻列表
        """
        news_list = []
        
        try:
            # 腾讯财经页面只爬取首页
            page_news = self._crawl_page(1)
            news_list.extend(page_news)
            logger.info(f"Crawled Tencent Finance, got {len(page_news)} news items")
        except Exception as e:
            logger.error(f"Error crawling Tencent Finance: {e}")
        
        # 应用股票筛选
        filtered_news = self._filter_stock_news(news_list)
        return filtered_news
    
    def _crawl_page(self, page: int) -> List[NewsItem]:
        """
        爬取单页新闻
        
        优先使用API获取新闻，如果API失败则回退到HTML解析
        
        Args:
            page: 页码
            
        Returns:
            新闻列表
        """
        news_items = []
        
        # 先尝试使用API获取新闻
        try:
            logger.info(f"[Tencent] Attempting API fetch for page {page}")
            api_news = self._fetch_api_news(page)
            logger.info(f"[Tencent] API returned {len(api_news) if api_news else 0} news items")
            if api_news:
                logger.info(f"Fetched {len(api_news)} news from API")
                for news_data in api_news[:20]:  # 限制20条
                    try:
                        news_item = self._parse_api_news_item(news_data)
                        if news_item:
                            news_items.append(news_item)
                    except Exception as e:
                        logger.warning(f"Failed to parse API news item: {e}")
                        continue
                if news_items:
                    logger.info(f"[Tencent] Successfully parsed {len(news_items)} news items from API")
                    return news_items
            else:
                logger.info(f"[Tencent] API returned empty list, falling back to HTML")
        except Exception as e:
            logger.warning(f"API fetch failed, fallback to HTML: {e}")
        
        # API失败，回退到HTML解析
        try:
            response = self._fetch_page(self.BASE_URL)
            # 腾讯新闻可能使用动态加载，确保编码正确
            if response.encoding == 'ISO-8859-1' or not response.encoding:
                response.encoding = 'utf-8'
            soup = self._parse_html(response.text)
            
            # 提取新闻列表
            # 腾讯的新闻可能在各种容器中，尝试提取所有新闻链接
            news_links = self._extract_news_links(soup)
            
            logger.info(f"Found {len(news_links)} potential news links from HTML")
            
            # 限制爬取数量，避免过多请求
            max_news = 20
            for i, link_info in enumerate(news_links[:max_news]):
                try:
                    news_item = self._extract_news_item(link_info)
                    if news_item:
                        news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Failed to extract news item {i+1}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error crawling page {page}: {e}")
        
        return news_items
    
    def _fetch_api_news(self, page: int = 0) -> List[dict]:
        """
        通过API获取新闻列表
        
        Args:
            page: 页码（从0开始）
            
        Returns:
            新闻列表
        """
        try:
            # 腾讯新闻API参数（根据实际API文档调整）
            params = {
                "cid": "finance_stock",  # 股票频道
                "page": page,
                "num": 20,  # 每页20条
                "ext": "finance_stock",  # 扩展参数
            }
            
            headers = {
                "User-Agent": self.user_agent,
                "Referer": self.BASE_URL,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }
            
            logger.info(f"[Tencent] Calling API: {self.API_URL} with params: {params}")
            response = self.session.get(
                self.API_URL,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            logger.info(f"[Tencent] API response status: {response.status_code}")
            response.raise_for_status()
            
            # 解析JSON响应（可能是JSONP格式）
            content = response.text.strip()
            logger.info(f"[Tencent] API response preview (first 500 chars): {content[:500]}")
            
            # 尝试解析JSONP格式
            if content.startswith('callback(') or content.startswith('jQuery'):
                # 提取JSON部分
                import re
                json_match = re.search(r'\((.*)\)$', content)
                if json_match:
                    content = json_match.group(1)
            
            data = json.loads(content)
            logger.info(f"[Tencent] Parsed API response type: {type(data)}, keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            
            if isinstance(data, dict):
                if 'data' in data:
                    logger.info(f"[Tencent] Found 'data' key with {len(data['data']) if isinstance(data['data'], list) else 'non-list'} items")
                    return data['data']
                elif 'list' in data:
                    logger.info(f"[Tencent] Found 'list' key with {len(data['list']) if isinstance(data['list'], list) else 'non-list'} items")
                    return data['list']
                elif 'result' in data:
                    logger.info(f"[Tencent] Found 'result' key with {len(data['result']) if isinstance(data['result'], list) else 'non-list'} items")
                    return data['result']
                else:
                    logger.warning(f"[Tencent] Unexpected API response format, keys: {list(data.keys())}")
            elif isinstance(data, list):
                logger.info(f"[Tencent] API returned list with {len(data)} items")
                return data
            
            logger.warning(f"Unexpected API response format: {type(data)}")
            return []
            
        except json.JSONDecodeError as e:
            logger.warning(f"API JSON decode failed: {e}, response preview: {response.text[:200] if 'response' in locals() else 'N/A'}")
            return []
        except Exception as e:
            logger.warning(f"API fetch failed: {e}")
            return []
    
    def _parse_api_news_item(self, news_data: dict) -> Optional[NewsItem]:
        """
        解析API返回的新闻数据
        
        Args:
            news_data: API返回的单条新闻数据
            
        Returns:
            NewsItem对象
        """
        try:
            # 提取基本信息
            title = news_data.get('title', '').strip()
            url = news_data.get('url', '') or news_data.get('surl', '')
            
            # 确保URL是完整的
            if url and not url.startswith('http'):
                if url.startswith('//'):
                    url = 'https:' + url
                elif url.startswith('/'):
                    url = 'https://news.qq.com' + url
                else:
                    url = 'https://news.qq.com/' + url.lstrip('/')
            
            if not title or not url:
                return None
            
            # 提取发布时间
            publish_time_str = news_data.get('time', '') or news_data.get('publish_time', '')
            publish_time = self._parse_time_string(publish_time_str) if publish_time_str else datetime.now()
            
            # 提取摘要作为内容（API通常不返回完整内容）
            content = news_data.get('abstract', '') or news_data.get('intro', '') or title
            
            # 提取作者
            author = news_data.get('author', '') or news_data.get('source', '')
            
            # 尝试获取完整内容
            try:
                response = self._fetch_page(url)
                if response.encoding == 'ISO-8859-1' or not response.encoding:
                    response.encoding = 'utf-8'
                raw_html = response.text
                soup = self._parse_html(raw_html)
                full_content = self._extract_content(soup)
                if full_content and len(full_content) > len(content):
                    content = full_content
            except Exception as e:
                logger.debug(f"Failed to fetch full content from {url}: {e}")
                raw_html = None
            
            return NewsItem(
                title=title,
                content=content,
                url=url,
                source=self.SOURCE_NAME,
                publish_time=publish_time,
                author=author if author else None,
                raw_html=raw_html,
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse API news item: {e}")
            return None
    
    def _extract_news_links(self, soup: BeautifulSoup) -> List[dict]:
        """
        从页面中提取新闻链接
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            新闻链接信息列表
        """
        news_links = []
        
        # 查找所有链接
        all_links = soup.find_all('a', href=True)
        
        # 腾讯新闻URL模式（扩展更多模式）
        tencent_patterns = [
            '/rain/a/',           # 旧模式
            '/omn/',              # 旧模式
            '/a/',                # 新模式
            '/finance/',          # 财经频道
            'finance.qq.com',     # 财经域名
            '/stock/',            # 股票相关
        ]
        
        for link in all_links:
            href = link.get('href', '')
            title = link.get_text(strip=True)
            
            # 检查是否匹配腾讯新闻URL模式
            is_tencent_url = False
            for pattern in tencent_patterns:
                if pattern in href:
                    is_tencent_url = True
                    break
            
            # 或者检查是否是qq.com域名且包含新闻相关关键词
            if not is_tencent_url:
                if 'qq.com' in href and any(kw in href for kw in ['/a/', '/article/', '/news/', '/finance/']):
                    is_tencent_url = True
            
            if is_tencent_url and title and len(title.strip()) > 5:
                # 确保是完整URL
                if not href.startswith('http'):
                    if href.startswith('//'):
                        href = 'https:' + href
                    elif href.startswith('/'):
                        href = 'https://news.qq.com' + href
                    else:
                        href = 'https://news.qq.com/' + href.lstrip('/')
                
                # 过滤掉明显不是新闻的链接
                if any(skip in href.lower() for skip in ['javascript:', 'mailto:', '#', 'void(0)']):
                    continue
                
                if href not in [n['url'] for n in news_links]:
                    news_links.append({
                        'url': href,
                        'title': title.strip()
                    })
        
        logger.debug(f"Tencent: Found {len(news_links)} potential news links")
        return news_links
    
    def _extract_news_item(self, link_info: dict) -> Optional[NewsItem]:
        """
        提取单条新闻详情
        
        Args:
            link_info: 新闻链接信息
            
        Returns:
            NewsItem或None
        """
        url = link_info['url']
        title = link_info['title']
        
        try:
            # 获取新闻详情页
            response = self._fetch_page(url)
            # 确保编码正确
            if response.encoding == 'ISO-8859-1' or not response.encoding:
                response.encoding = 'utf-8'
            raw_html = response.text  # 保存原始 HTML
            soup = self._parse_html(raw_html)
            
            # 提取正文内容
            content = self._extract_content(soup)
            if not content:
                logger.debug(f"No content found for: {title}")
                return None
            
            # 提取发布时间
            publish_time = self._extract_publish_time(soup)
            
            # 提取作者
            author = self._extract_author(soup)
            
            return NewsItem(
                title=title,
                content=content,
                url=url,
                source=self.SOURCE_NAME,
                publish_time=publish_time,
                author=author,
                raw_html=raw_html,  # 保存原始 HTML
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract news from {url}: {e}")
            return None
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """
        提取新闻正文
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            新闻正文
        """
        # 尝试多种选择器
        content_selectors = [
            {'class': 'content-article'},
            {'class': 'LEFT'},
            {'id': 'Cnt-Main-Article-QQ'},
            {'class': 'article'},
        ]
        
        for selector in content_selectors:
            content_div = soup.find('div', selector)
            if content_div:
                # 获取所有段落
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    content = '\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    if content:
                        return self._clean_text(content)
        
        # 后备方案：使用基类的智能提取方法
        return self._extract_article_content(soup)
    
    def _extract_publish_time(self, soup: BeautifulSoup) -> Optional[datetime]:
        """
        提取发布时间
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            发布时间
        """
        try:
            # 尝试多种时间选择器
            time_selectors = [
                {'class': 'a-time'},
                {'class': 'article-time'},
                {'class': 'time'},
            ]
            
            for selector in time_selectors:
                time_elem = soup.find('span', selector)
                if time_elem:
                    time_str = time_elem.get_text(strip=True)
                    return self._parse_time_string(time_str)
            
            # 尝试从meta标签获取
            meta_time = soup.find('meta', {'property': 'article:published_time'})
            if meta_time and meta_time.get('content'):
                return datetime.fromisoformat(meta_time['content'].replace('Z', '+00:00'))
            
        except Exception as e:
            logger.debug(f"Failed to parse publish time: {e}")
        
        # 默认返回当前时间
        return datetime.now()
    
    def _parse_time_string(self, time_str: str) -> datetime:
        """
        解析时间字符串（如"1小时前"、"昨天"、"2024-12-06 10:00"）
        
        Args:
            time_str: 时间字符串
            
        Returns:
            datetime对象
        """
        now = datetime.now()
        
        # 处理相对时间
        if '分钟前' in time_str:
            minutes = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(minutes=minutes)
        elif '小时前' in time_str:
            hours = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(hours=hours)
        elif '昨天' in time_str:
            return now - timedelta(days=1)
        elif '前天' in time_str:
            return now - timedelta(days=2)
        
        # 尝试解析绝对时间
        try:
            # 尝试多种格式
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%Y-%m-%d',
                '%Y年%m月%d日 %H:%M',
                '%Y年%m月%d日',
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        
        # 默认返回当前时间
        return now
    
    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """
        提取作者
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            作者名称
        """
        try:
            # 尝试多种作者选择器
            author_selectors = [
                {'class': 'author'},
                {'class': 'article-author'},
                {'class': 'source'},
            ]
            
            for selector in author_selectors:
                author_elem = soup.find('span', selector) or soup.find('a', selector)
                if author_elem:
                    author = author_elem.get_text(strip=True)
                    if author:
                        return author
        except Exception as e:
            logger.debug(f"Failed to extract author: {e}")
        
        return None

