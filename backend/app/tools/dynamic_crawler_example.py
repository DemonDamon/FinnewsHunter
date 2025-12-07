"""
动态网站爬虫示例 - 使用 Selenium
适用于需要点击"加载更多"的网站

依赖安装：
pip install selenium webdriver-manager
"""
import logging
from typing import List, Optional
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from .crawler_base import BaseCrawler, NewsItem

logger = logging.getLogger(__name__)


class DynamicCrawlerExample(BaseCrawler):
    """
    动态网站爬虫示例
    支持点击"加载更多"按钮
    """
    
    BASE_URL = "https://www.eeo.com.cn/"
    STOCK_URL = "https://www.eeo.com.cn/jg/jinrong/zhengquan/"
    SOURCE_NAME = "eeo_dynamic"
    
    def __init__(self):
        super().__init__(
            name="eeo_dynamic_crawler",
            description="Crawl EEO with dynamic loading support"
        )
        self.driver = None
    
    def _init_driver(self):
        """初始化 Selenium WebDriver"""
        if self.driver:
            return
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 无头模式
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument(f'user-agent={self.user_agent}')
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("Selenium WebDriver initialized")
    
    def _close_driver(self):
        """关闭 WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def crawl(self, start_page: int = 1, end_page: int = 1) -> List[NewsItem]:
        """
        爬取新闻（支持动态加载）
        
        Args:
            start_page: 起始页（对于点击加载更多的网站，这个参数表示点击次数）
            end_page: 结束页
            
        Returns:
            新闻列表
        """
        news_list = []
        
        try:
            self._init_driver()
            page_news = self._crawl_with_selenium()
            news_list.extend(page_news)
            logger.info(f"Crawled EEO (dynamic), got {len(page_news)} news items")
        except Exception as e:
            logger.error(f"Error crawling EEO (dynamic): {e}")
        finally:
            self._close_driver()
        
        # 应用股票筛选
        filtered_news = self._filter_stock_news(news_list)
        return filtered_news
    
    def _crawl_with_selenium(self) -> List[NewsItem]:
        """使用 Selenium 爬取动态加载的内容"""
        news_items = []
        
        try:
            # 1. 访问页面
            self.driver.get(self.STOCK_URL)
            logger.info(f"Loaded page: {self.STOCK_URL}")
            
            # 2. 等待页面加载
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 3. 尝试点击"加载更多"按钮（如果存在）
            click_count = 0
            max_clicks = 3  # 最多点击3次"加载更多"
            
            while click_count < max_clicks:
                try:
                    # 查找"加载更多"按钮（根据实际页面调整选择器）
                    load_more_button = self.driver.find_element(
                        By.XPATH, 
                        "//button[contains(text(), '加载更多')] | //div[contains(text(), '点击加载更多')]"
                    )
                    
                    # 滚动到按钮位置
                    self.driver.execute_script("arguments[0].scrollIntoView();", load_more_button)
                    
                    # 点击按钮
                    load_more_button.click()
                    click_count += 1
                    logger.info(f"Clicked 'Load More' button {click_count} times")
                    
                    # 等待新内容加载
                    import time
                    time.sleep(2)
                    
                except Exception as e:
                    logger.debug(f"No more 'Load More' button or click failed: {e}")
                    break
            
            # 4. 提取所有新闻链接
            news_links = self._extract_news_links_from_selenium()
            logger.info(f"Found {len(news_links)} news links")
            
            # 5. 爬取每条新闻的详情
            max_news = 20
            for link_info in news_links[:max_news]:
                try:
                    news_item = self._extract_news_item(link_info)
                    if news_item:
                        news_items.append(news_item)
                except Exception as e:
                    logger.warning(f"Failed to extract news item: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error in Selenium crawling: {e}")
        
        return news_items
    
    def _extract_news_links_from_selenium(self) -> List[dict]:
        """从 Selenium 页面中提取新闻链接"""
        news_links = []
        
        try:
            # 查找所有新闻链接（根据实际页面结构调整选择器）
            link_elements = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/article/']")
            
            for element in link_elements:
                try:
                    href = element.get_attribute('href')
                    title = element.text.strip()
                    
                    if href and title and href not in [n['url'] for n in news_links]:
                        news_links.append({'url': href, 'title': title})
                except Exception as e:
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting links: {e}")
        
        return news_links
    
    def _extract_news_item(self, link_info: dict) -> Optional[NewsItem]:
        """提取单条新闻详情（使用传统 requests 方式）"""
        url = link_info['url']
        title = link_info['title']
        
        try:
            response = self._fetch_page(url)
            soup = self._parse_html(response.text)
            
            # 提取正文（简化示例）
            content_div = soup.find('div', class_='article-content')
            if content_div:
                content = content_div.get_text(strip=True)
            else:
                content = ""
            
            if not content:
                return None
            
            return NewsItem(
                title=title,
                content=self._clean_text(content),
                url=url,
                source=self.SOURCE_NAME,
                publish_time=datetime.now(),
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract news from {url}: {e}")
            return None


# 使用示例
if __name__ == "__main__":
    crawler = DynamicCrawlerExample()
    news = crawler.crawl()
    print(f"Crawled {len(news)} news items")
    for item in news[:5]:
        print(f"- {item.title}")

