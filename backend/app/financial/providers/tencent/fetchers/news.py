"""
腾讯财经新闻 Fetcher

基于 TET Pipeline 实现:
- Transform Query: 转换标准参数为腾讯财经特定参数
- Extract Data: 从腾讯财经抓取原始数据
- Transform Data: 转换为标准 NewsData 格式
"""
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests

from ...base import BaseFetcher
from ....models.news import NewsQueryParams, NewsData, NewsSentiment

logger = logging.getLogger(__name__)


class TencentNewsFetcher(BaseFetcher):
    """
    腾讯财经新闻 Fetcher
    
    数据源: https://news.qq.com/ch/finance/
    """
    
    BASE_URL = "https://news.qq.com/ch/finance/"
    SOURCE_NAME = "tencent"
    
    # 请求配置
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    def transform_query(self, params: NewsQueryParams) -> Dict[str, Any]:
        """
        转换标准查询参数为腾讯财经特定参数
        """
        return {
            "url": self.BASE_URL,
            "limit": params.limit or 20,
            "stock_codes": params.stock_codes,
            "keywords": params.keywords,
        }
    
    def extract_data(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从腾讯财经抓取原始新闻数据
        """
        raw_news = []
        
        try:
            response = requests.get(
                query["url"],
                headers=self.HEADERS,
                timeout=30
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            news_links = self._extract_news_links(soup)
            
            logger.info(f"[Tencent] Found {len(news_links)} news links")
            
            # 限制获取数量
            max_fetch = min(query["limit"], 20)
            
            for link_info in news_links[:max_fetch]:
                try:
                    news_item = self._fetch_news_detail(link_info)
                    if news_item:
                        raw_news.append(news_item)
                except Exception as e:
                    logger.warning(f"[Tencent] Failed to fetch {link_info['url']}: {e}")
                    continue
            
            logger.info(f"[Tencent] Extracted {len(raw_news)} news items")
            
        except Exception as e:
            logger.error(f"[Tencent] Extract failed: {e}")
        
        return raw_news
    
    def transform_data(
        self,
        raw_data: List[Dict[str, Any]],
        params: NewsQueryParams
    ) -> List[NewsData]:
        """
        转换原始数据为标准 NewsData 格式
        """
        news_list = []
        
        for item in raw_data:
            try:
                # 提取股票代码
                stock_codes = self._extract_stock_codes(
                    item.get("title", "") + " " + item.get("content", "")
                )
                
                # 过滤：如果指定了股票代码，只保留相关新闻
                if params.stock_codes:
                    if not any(code in stock_codes for code in params.stock_codes):
                        continue
                
                # 过滤：关键词过滤
                if params.keywords:
                    text = item.get("title", "") + " " + item.get("content", "")
                    if not any(kw in text for kw in params.keywords):
                        continue
                
                news = NewsData(
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    source=self.SOURCE_NAME,
                    source_url=item.get("url", ""),
                    publish_time=item.get("publish_time", datetime.now()),
                    author=item.get("author"),
                    stock_codes=stock_codes,
                    sentiment=NewsSentiment.NEUTRAL,  # 默认中性
                )
                news_list.append(news)
                
            except Exception as e:
                logger.warning(f"[Tencent] Transform failed for item: {e}")
                continue
        
        # 应用 limit
        if params.limit:
            news_list = news_list[:params.limit]
        
        return news_list
    
    def _extract_news_links(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """从页面提取新闻链接"""
        news_links = []
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '')
            
            # 腾讯新闻URL模式
            if '/rain/a/' in href or '/omn/' in href:
                if not href.startswith('http'):
                    href = 'https:' + href if href.startswith('//') else 'https://news.qq.com' + href
                
                title = link.get_text(strip=True)
                if title and href not in [n['url'] for n in news_links]:
                    news_links.append({'url': href, 'title': title})
        
        return news_links
    
    def _fetch_news_detail(self, link_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """获取新闻详情"""
        url = link_info['url']
        title = link_info['title']
        
        try:
            response = requests.get(url, headers=self.HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            content = self._extract_content(soup)
            if not content:
                return None
            
            publish_time = self._extract_publish_time(soup)
            author = self._extract_author(soup)
            
            return {
                "title": title,
                "content": content,
                "url": url,
                "publish_time": publish_time,
                "author": author,
            }
            
        except Exception as e:
            logger.debug(f"[Tencent] Detail fetch failed: {e}")
            return None
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取新闻正文"""
        content_selectors = [
            {'class': 'content-article'},
            {'class': 'LEFT'},
            {'id': 'Cnt-Main-Article-QQ'},
            {'class': 'article'},
        ]
        
        for selector in content_selectors:
            content_div = soup.find('div', selector)
            if content_div:
                paragraphs = content_div.find_all('p')
                if paragraphs:
                    content = '\n'.join([
                        p.get_text(strip=True) for p in paragraphs 
                        if p.get_text(strip=True)
                    ])
                    if content:
                        return self._clean_text(content)
        
        return ""
    
    def _extract_publish_time(self, soup: BeautifulSoup) -> datetime:
        """提取发布时间"""
        try:
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
            
            meta_time = soup.find('meta', {'property': 'article:published_time'})
            if meta_time and meta_time.get('content'):
                return datetime.fromisoformat(meta_time['content'].replace('Z', '+00:00'))
            
        except Exception:
            pass
        
        return datetime.now()
    
    def _parse_time_string(self, time_str: str) -> datetime:
        """解析时间字符串"""
        now = datetime.now()
        
        if '分钟前' in time_str:
            minutes = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(minutes=minutes)
        elif '小时前' in time_str:
            hours = int(re.search(r'(\d+)', time_str).group(1))
            return now - timedelta(hours=hours)
        elif '昨天' in time_str:
            return now - timedelta(days=1)
        
        formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']
        for fmt in formats:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        
        return now
    
    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """提取作者"""
        try:
            for selector in [{'class': 'author'}, {'class': 'source'}]:
                elem = soup.find('span', selector) or soup.find('a', selector)
                if elem:
                    return elem.get_text(strip=True)
        except Exception:
            pass
        return None
    
    def _extract_stock_codes(self, text: str) -> List[str]:
        """从文本提取股票代码"""
        patterns = [
            r'(\d{6})\.(SH|SZ|sh|sz)',
            r'(SH|SZ|sh|sz)(\d{6})',
            r'[（(](\d{6})[)）]',
        ]
        
        codes = set()
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    code = ''.join(match)
                else:
                    code = match
                code = re.sub(r'[^0-9]', '', code)
                if len(code) == 6:
                    codes.add(code)
        
        return list(codes)
    
    def _clean_text(self, text: str) -> str:
        """清理文本"""
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text
