"""
经济观察网爬虫工具
目标URL: https://www.eeo.com.cn/jg/jinrong/zhengquan/
"""
import re
import json
import logging
from typing import List, Optional
from datetime import datetime
from bs4 import BeautifulSoup

from .crawler_base import BaseCrawler, NewsItem

logger = logging.getLogger(__name__)


class EeoCrawlerTool(BaseCrawler):
    """
    经济观察网爬虫
    主要爬取证券栏目
    使用官方API接口
    """
    
    BASE_URL = "https://www.eeo.com.cn/"
    # 证券栏目URL（用于获取uuid）
    STOCK_URL = "https://www.eeo.com.cn/jg/jinrong/zhengquan/"
    # API接口URL
    API_URL = "https://app.eeo.com.cn/"
    SOURCE_NAME = "eeo"
    # 证券频道的UUID（通过访问页面获取）
    CHANNEL_UUID = "9905934f8ec548ddae87652dbb9eebc6"
    
    def __init__(self):
        super().__init__(
            name="eeo_crawler",
            description="Crawl financial news from Economic Observer (eeo.com.cn)"
        )
    
    def crawl(self, start_page: int = 1, end_page: int = 1) -> List[NewsItem]:
        """
        爬取经济观察网新闻
        
        Args:
            start_page: 起始页码
            end_page: 结束页码
            
        Returns:
            新闻列表
        """
        news_list = []
        
        try:
            page_news = self._crawl_page(1)
            news_list.extend(page_news)
            logger.info(f"Crawled EEO, got {len(page_news)} news items")
        except Exception as e:
            logger.error(f"Error crawling EEO: {e}")
        
        # 应用股票筛选
        filtered_news = self._filter_stock_news(news_list)
        return filtered_news
    
    def _fetch_api_news(self, page: int = 0, prev_uuid: str = "", prev_publish_date: str = "") -> List[dict]:
        """
        通过API获取新闻列表
        
        Args:
            page: 页码（从0开始）
            prev_uuid: 上一条新闻的UUID（用于翻页）
            prev_publish_date: 上一条新闻的发布时间（用于翻页）
            
        Returns:
            新闻列表
        """
        try:
            # 构建API参数
            params = {
                "app": "article",
                "controller": "index",
                "action": "getMoreArticle",
                "uuid": self.CHANNEL_UUID,
                "page": page,
                "pageSize": 20,  # 每页20条
                "prevUuid": prev_uuid,
                "prevPublishDate": prev_publish_date,
            }
            
            # 添加必要的请求头
            headers = {
                "User-Agent": self.user_agent,
                "Referer": self.STOCK_URL,
                "Accept": "*/*",
            }
            
            response = self.session.get(
                self.API_URL,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # 处理JSONP响应
            # 响应格式: jQuery11130...callback({"status":1,"data":[...]})
            content = response.text
            
            # 提取JSON部分（去掉JSONP包装）
            json_match = re.search(r'\((.*)\)$', content)
            if json_match:
                json_str = json_match.group(1)
                data = json.loads(json_str)
                
                if data.get('status') == 1 and 'data' in data:
                    return data['data']
            
            logger.warning(f"Failed to parse API response")
            return []
            
        except Exception as e:
            logger.error(f"API fetch failed: {e}")
            return []
    
    def _crawl_page(self, page: int) -> List[NewsItem]:
        """
        爬取单页新闻（使用API）
        
        Args:
            page: 页码
            
        Returns:
            新闻列表
        """
        news_items = []
        
        try:
            # 使用API获取新闻列表
            api_news_list = self._fetch_api_news(page=0)  # 第一页
            
            if not api_news_list:
                logger.warning("No news from API, fallback to HTML parsing")
                return self._crawl_page_html()
            
            logger.info(f"Fetched {len(api_news_list)} news from API")
            
            # 解析每条新闻
            for news_data in api_news_list[:20]:  # 限制20条
                try:
                    news_item = self._parse_api_news_item(news_data)
                    if news_item:
                        news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Failed to parse news item: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error crawling page: {e}")
        
        return news_items
    
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
            url = news_data.get('url', '')
            
            # 确保URL是完整的
            if url and not url.startswith('http'):
                url = 'https://www.eeo.com.cn' + url
            
            if not title or not url:
                return None
            
            # 提取发布时间
            publish_time_str = news_data.get('publishDate', '')
            publish_time = self._parse_time_string(publish_time_str) if publish_time_str else datetime.now()
            
            # 提取作者
            author = news_data.get('author', '')
            
            # 获取新闻详情（内容和原始HTML）
            content, raw_html = self._fetch_news_content(url)
            
            if not content:
                return None
            
            return NewsItem(
                title=title,
                content=content,
                url=url,
                source=self.SOURCE_NAME,
                publish_time=publish_time,
                author=author if author else None,
                raw_html=raw_html,  # 保存原始 HTML
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse API news item: {e}")
            return None
    
    def _fetch_news_content(self, url: str) -> tuple:
        """
        获取新闻详情页内容
        
        Args:
            url: 新闻详情页URL
            
        Returns:
            (新闻正文, 原始HTML)
        """
        try:
            response = self._fetch_page(url)
            raw_html = response.text  # 保存原始 HTML
            soup = self._parse_html(raw_html)
            
            # 提取正文
            content = self._extract_content(soup)
            return content, raw_html
            
        except Exception as e:
            logger.warning(f"Failed to fetch content from {url}: {e}")
            return "", ""
    
    def _crawl_page_html(self) -> List[NewsItem]:
        """
        备用方案：直接解析HTML页面（只能获取首屏内容）
        """
        news_items = []
        
        try:
            response = self._fetch_page(self.STOCK_URL)
            soup = self._parse_html(response.text)
            
            # 提取新闻列表
            news_links = self._extract_news_links(soup)
            logger.info(f"Found {len(news_links)} potential news links from HTML")
            
            # 限制爬取数量
            max_news = 10
            for link_info in news_links[:max_news]:
                try:
                    news_item = self._extract_news_item(link_info)
                    if news_item:
                        news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Failed to extract news item: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error crawling HTML page: {e}")
        
        return news_items
    
    def _extract_news_links(self, soup: BeautifulSoup) -> List[dict]:
        """从页面中提取新闻链接"""
        news_links = []
        
        # 查找新闻链接
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '')
            title = link.get_text(strip=True)
            
            # 经济观察网新闻URL模式
            if ('/\d{4}/' in href or '.shtml' in href) and title:
                # 确保是完整URL
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    href = 'https://www.eeo.com.cn' + href
                elif not href.startswith('http'):
                    href = 'https://www.eeo.com.cn/' + href.lstrip('/')
                
                if href not in [n['url'] for n in news_links]:
                    news_links.append({'url': href, 'title': title})
        
        return news_links
    
    def _extract_news_item(self, link_info: dict) -> Optional[NewsItem]:
        """提取单条新闻详情（HTML方式）"""
        url = link_info['url']
        title = link_info['title']
        
        try:
            response = self._fetch_page(url)
            raw_html = response.text  # 保存原始 HTML
            soup = self._parse_html(raw_html)
            
            # 提取正文
            content = self._extract_content(soup)
            if not content:
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
        """提取新闻正文"""
        content_selectors = [
            {'class': 'article-content'},
            {'class': 'content'},
            {'id': 'articleContent'},
            {'class': 'news-content'},
            {'class': 'text_content'},  # 常见的正文类名
        ]
        
        for selector in content_selectors:
            content_div = soup.find(['div', 'article'], selector)
            if content_div:
                # 1. 移除明确的噪音元素
                for tag in content_div.find_all(['script', 'style', 'iframe', 'ins', 'select', 'input', 'button', 'form']):
                    tag.decompose()
                
                # 2. 移除特定的广告和推荐块
                for ad in content_div.find_all(class_=re.compile(r'ad|banner|share|otherContent|recommend|app-guide|qrcode', re.I)):
                    ad.decompose()

                # 3. 获取所有文本，使用换行符分隔
                # 关键修改：使用 get_text 而不是 find_all('p')
                full_text = content_div.get_text(separator='\n', strip=True)
                
                # 4. 按行分割并清洗
                lines = full_text.split('\n')
                article_parts = []
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    # 5. 简单的长度过滤，防止页码等噪音
                    if len(line) < 2:
                        continue
                        
                    article_parts.append(line)
                
                if article_parts:
                    content = '\n'.join(article_parts)
                    return self._clean_text(content)
        
        # 后备方案：使用基类的智能提取方法
        return self._extract_article_content(soup)
    
    def _extract_publish_time(self, soup: BeautifulSoup) -> Optional[datetime]:
        """提取发布时间"""
        try:
            time_elem = soup.find('span', {'class': re.compile(r'time|date')})
            if time_elem:
                time_str = time_elem.get_text(strip=True)
                return self._parse_time_string(time_str)
        except Exception as e:
            logger.debug(f"Failed to parse publish time: {e}")
        
        return datetime.now()
    
    def _parse_time_string(self, time_str: str) -> datetime:
        """解析时间字符串"""
        now = datetime.now()
        
        # 尝试解析绝对时间
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
        
        return now
    
    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """提取作者"""
        try:
            author_elem = soup.find('span', {'class': re.compile(r'author|source')})
            if author_elem:
                return author_elem.get_text(strip=True)
        except Exception as e:
            logger.debug(f"Failed to extract author: {e}")
        
        return None
