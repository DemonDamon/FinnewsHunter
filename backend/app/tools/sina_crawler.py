"""
新浪财经爬虫工具
重构自 legacy_v1/Crawler/crawler_sina.py
"""
import re
import logging
from typing import List, Optional
from datetime import datetime
from bs4 import BeautifulSoup

from .crawler_base import BaseCrawler, NewsItem

logger = logging.getLogger(__name__)


class SinaCrawlerTool(BaseCrawler):
    """
    新浪财经新闻爬虫
    爬取 http://roll.finance.sina.com.cn/finance/zq1/ssgs/index_页码.shtml
    """
    
    BASE_URL = "http://roll.finance.sina.com.cn/finance/zq1/ssgs/index_{}.shtml"
    SOURCE_NAME = "sina"
    
    def __init__(self):
        super().__init__(
            name="sina_finance_crawler",
            description="Crawl financial news from Sina Finance (sina.com.cn)"
        )
        self.min_chinese_ratio = 0.5  # 最小中文比例阈值
    
    def crawl(self, start_page: int = 1, end_page: int = 1) -> List[NewsItem]:
        """
        爬取新浪财经新闻
        
        Args:
            start_page: 起始页码
            end_page: 结束页码
            
        Returns:
            新闻列表
        """
        news_list = []
        
        for page in range(start_page, end_page + 1):
            try:
                page_news = self._crawl_page(page)
                news_list.extend(page_news)
                logger.info(f"Crawled page {page}, got {len(page_news)} news items")
            except Exception as e:
                logger.error(f"Failed to crawl page {page}: {e}")
                continue
        
        return news_list
    
    def _crawl_page(self, page: int) -> List[NewsItem]:
        """
        爬取单页新闻列表
        
        Args:
            page: 页码（页码1通常是最新新闻）
            
        Returns:
            新闻列表
        """
        url = self.BASE_URL.format(page)
        logger.info(f"Fetching page: {url}")
        response = self._fetch_page(url)
        
        # 设置正确的编码
        response.encoding = 'utf-8'
        soup = self._parse_html(response.text)
        
        # 查找新闻链接（改进选择器，更精确地找到新闻链接）
        news_links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            # 匹配新浪财经股票相关新闻URL
            if 'finance.sina.com.cn' in href and ('/stock/' in href or '/roll/' in href):
                # 确保是完整的URL
                if href.startswith('http'):
                    news_links.append(href)
                elif href.startswith('//'):
                    news_links.append('http:' + href)
        
        # 去重
        news_links = list(set(news_links))
        logger.info(f"Found {len(news_links)} news links on page {page}")
        
        # 爬取每条新闻详情（限制每页最多50条，避免超时）
        news_list = []
        max_news_per_page = 50 if page == 1 else 30  # 第一页爬取更多，其他页少一些
        for idx, news_url in enumerate(news_links[:max_news_per_page], 1):
            try:
                logger.debug(f"Crawling news {idx}/{min(len(news_links), max_news_per_page)}: {news_url}")
                news_item = self._crawl_news_detail(news_url)
                if news_item:
                    news_list.append(news_item)
                    logger.debug(f"Successfully crawled: {news_item.title[:50]}")
            except Exception as e:
                logger.warning(f"Failed to crawl news detail {news_url}: {e}")
                continue
        
        logger.info(f"Successfully crawled {len(news_list)} news items from page {page}")
        return news_list
    
    def _crawl_news_detail(self, url: str) -> Optional[NewsItem]:
        """
        爬取新闻详情页
        
        Args:
            url: 新闻URL
            
        Returns:
            新闻项或None
        """
        try:
            response = self._fetch_page(url)
            response.encoding = BeautifulSoup(response.content, "lxml").original_encoding
            soup = self._parse_html(response.text)
            
            # 提取标题
            title = self._extract_title(soup)
            if not title:
                return None
            
            # 提取摘要和关键词
            summary, keywords = self._extract_meta(soup)
            
            # 提取发布时间
            publish_time = self._extract_date(soup)
            
            # 提取关联股票代码
            stock_codes = self._extract_stock_codes(soup)
            
            # 提取正文
            content = self._extract_content(soup)
            if not content or len(content) < 50:
                return None
            
            return NewsItem(
                title=title,
                content=content,
                url=url,
                source=self.SOURCE_NAME,
                publish_time=publish_time,
                summary=summary,
                keywords=keywords,
                stock_codes=stock_codes,
            )
            
        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")
            return None
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """提取标题"""
        # 尝试多个可能的标题位置
        title_tag = soup.find('h1', class_='main-title')
        if not title_tag:
            title_tag = soup.find('h1')
        if not title_tag:
            title_tag = soup.find('title')
        
        if title_tag:
            title = title_tag.get_text().strip()
            # 移除来源信息
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
        # 查找时间标签
        for span in soup.find_all('span'):
            # 检查 class 属性
            class_attr = span.get('class', [])
            if 'date' in class_attr or 'time-source' in class_attr:
                date_text = span.get_text()
                return self._parse_date(date_text)
            
            # 检查 id 属性
            if span.get('id') == 'pub_date':
                date_text = span.get_text()
                return self._parse_date(date_text)
        
        return None
    
    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """解析日期字符串"""
        try:
            # 格式：2024年12月01日 10:30
            date_text = date_text.strip()
            date_text = date_text.replace('年', '-').replace('月', '-').replace('日', '')
            
            # 尝试多种格式
            for fmt in [
                '%Y-%m-%d %H:%M',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
            ]:
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
                # 格式：stock_sh600519
                code = span_id[6:]  # 移除 'stock_' 前缀
                if code:
                    stock_codes.append(code.upper())
        
        return list(set(stock_codes))
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取正文内容"""
        # 查找所有段落
        paragraphs = soup.find_all('p')
        
        article_parts = []
        for p in paragraphs:
            text = p.get_text()
            
            # 检查中文比例
            chinese_ratio = self._extract_chinese_ratio(text)
            if chinese_ratio > self.min_chinese_ratio:
                clean_text = self._clean_text(text)
                if clean_text:
                    article_parts.append(clean_text)
        
        # 合并所有段落
        content = '\n'.join(article_parts)
        return content.strip()


# 便捷创建函数
def create_sina_crawler() -> SinaCrawlerTool:
    """创建新浪财经爬虫实例"""
    return SinaCrawlerTool()

