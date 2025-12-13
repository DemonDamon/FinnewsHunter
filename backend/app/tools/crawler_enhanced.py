"""
增强版爬虫模块
整合 deer-flow、BasicWebCrawler 和现有爬虫的优点

特性：
1. 多引擎支持：本地爬取 + Jina Reader API + Playwright JS 渲染
2. 智能内容提取：readabilipy + 启发式算法
3. 网站特定配置
4. 内容质量评估与自动重试
5. 缓存和去重
6. 统一 Article 模型，支持 LLM 消息格式
"""
import re
import os
import json
import time
import hashlib
import logging
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

# 可选依赖
try:
    from markdownify import markdownify as md
except ImportError:
    md = None

try:
    from readabilipy import simple_json_from_html_string
except ImportError:
    simple_json_from_html_string = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

logger = logging.getLogger(__name__)


# ============ 配置 ============

# 财经新闻网站特定配置
FINANCE_SITE_CONFIGS = {
    # 新浪财经
    'finance.sina.com.cn': {
        'main_content_selectors': [
            '.article-content', '.article', '#artibody', 
            '.main-content', '.post-body'
        ],
        'title_selectors': ['h1.main-title', 'h1', '.article-title'],
        'time_selectors': ['.date', '.pub_date', '.time-source'],
        'needs_js': False,
        'headers': {
            'Referer': 'https://finance.sina.com.cn/',
        }
    },
    # 东方财富
    'eastmoney.com': {
        'main_content_selectors': [
            '.article-content', '#ContentBody', '.newsContent',
            '.article', '.content-article'
        ],
        'needs_js': True,
        'wait_selectors': ['.article-content', '#ContentBody'],
    },
    # 每经网
    'nbd.com.cn': {
        'main_content_selectors': [
            '.article-content', '.g-article-content', 
            '.article-detail', '.post-content'
        ],
        'needs_js': False,
    },
    # 财新
    'caixin.com': {
        'main_content_selectors': [
            '#Main_Content_Val', '.article-content', 
            '.articleBody', '.main-content'
        ],
        'needs_cookies': True,  # 付费内容
        'needs_js': False,
    },
    # 腾讯财经
    'finance.qq.com': {
        'main_content_selectors': [
            '.content-article', '.Cnt-Main-Article-QQ',
            '#Cnt-Main-Article-QQ', '.article-content'
        ],
        'needs_js': False,
    },
    # 21世纪经济报道
    '21jingji.com': {
        'main_content_selectors': [
            '.article-content', '.detailContent', 
            '.article-body', '.post-content'
        ],
        'needs_js': False,
    },
    # 默认配置
    'default': {
        'main_content_selectors': [
            'article', 'main', '.article', '.content', 
            '.post-content', '.entry-content', '#content'
        ],
        'needs_js': False,
        'headers': {}
    }
}


# ============ Article 模型 ============

@dataclass
class Article:
    """
    统一的文章模型（参考 deer-flow）
    支持转换为 Markdown 和 LLM 消息格式
    """
    title: str
    content: str  # 纯文本内容
    html_content: Optional[str] = None  # 原始 HTML
    url: str = ""
    source: str = ""
    publish_time: Optional[datetime] = None
    author: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    stock_codes: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    
    # 元数据
    crawl_time: datetime = field(default_factory=datetime.utcnow)
    engine_used: str = ""  # 使用的爬取引擎
    quality_score: float = 0.0  # 内容质量评分
    
    def to_markdown(self, include_title: bool = True, include_meta: bool = False) -> str:
        """转换为 Markdown 格式"""
        parts = []
        
        if include_title and self.title:
            parts.append(f"# {self.title}\n")
        
        if include_meta:
            meta = []
            if self.source:
                meta.append(f"来源: {self.source}")
            if self.publish_time:
                meta.append(f"时间: {self.publish_time.strftime('%Y-%m-%d %H:%M')}")
            if self.author:
                meta.append(f"作者: {self.author}")
            if self.url:
                meta.append(f"原文: {self.url}")
            if meta:
                parts.append(f"*{' | '.join(meta)}*\n")
        
        # 如果有 HTML 内容且安装了 markdownify，转换它
        if self.html_content and md:
            parts.append(md(self.html_content))
        else:
            parts.append(self.content)
        
        return "\n".join(parts)
    
    def to_llm_message(self) -> List[Dict[str, Any]]:
        """
        转换为 LLM 消息格式（参考 deer-flow）
        将图片和文本分离，便于多模态 LLM 处理
        """
        content: List[Dict[str, str]] = []
        markdown = self.to_markdown()
        
        if not markdown.strip():
            return [{"type": "text", "text": "No content available"}]
        
        # 提取图片 URL
        image_pattern = r"!\[.*?\]\((.*?)\)"
        parts = re.split(image_pattern, markdown)
        
        for i, part in enumerate(parts):
            if i % 2 == 1:  # 图片 URL
                image_url = urljoin(self.url, part.strip())
                content.append({
                    "type": "image_url", 
                    "image_url": {"url": image_url}
                })
            else:  # 文本内容
                text_part = part.strip()
                if text_part:
                    content.append({"type": "text", "text": text_part})
        
        return content if content else [{"type": "text", "text": "No content available"}]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "title": self.title,
            "content": self.content,
            "html_content": self.html_content,
            "url": self.url,
            "source": self.source,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "author": self.author,
            "keywords": self.keywords,
            "stock_codes": self.stock_codes,
            "images": self.images,
            "crawl_time": self.crawl_time.isoformat(),
            "engine_used": self.engine_used,
            "quality_score": self.quality_score,
        }


# ============ 内容提取器 ============

class ContentExtractor:
    """
    智能内容提取器
    结合 readabilipy 和启发式算法
    """
    
    @staticmethod
    def extract_with_readability(html: str) -> Optional[Article]:
        """使用 readabilipy 提取（参考 deer-flow）"""
        if simple_json_from_html_string is None:
            return None
        
        try:
            result = simple_json_from_html_string(html, use_readability=True)
            content = result.get("content", "")
            title = result.get("title", "Untitled")
            
            if not content or len(content.strip()) < 100:
                return None
            
            return Article(
                title=title,
                content=BeautifulSoup(content, 'html.parser').get_text(separator='\n', strip=True),
                html_content=content,
            )
        except Exception as e:
            logger.warning(f"Readability extraction failed: {e}")
            return None
    
    @staticmethod
    def extract_with_selectors(soup: BeautifulSoup, config: dict) -> Optional[Article]:
        """使用 CSS 选择器提取"""
        # 提取标题
        title = None
        for sel in config.get('title_selectors', ['h1', 'title']):
            el = soup.select_one(sel)
            if el:
                title = el.get_text(strip=True)
                break
        
        if not title:
            title_el = soup.find('title')
            title = title_el.get_text(strip=True) if title_el else "Untitled"
        
        # 提取主要内容
        content_el = None
        for sel in config.get('main_content_selectors', []):
            content_el = soup.select_one(sel)
            if content_el and len(content_el.get_text(strip=True)) > 100:
                break
        
        if not content_el:
            return None
        
        # 清理内容
        for tag in content_el.find_all(['script', 'style', 'nav', 'footer', 'aside']):
            tag.decompose()
        
        content = content_el.get_text(separator='\n', strip=True)
        html_content = str(content_el)
        
        if len(content) < 100:
            return None
        
        return Article(
            title=title,
            content=content,
            html_content=html_content,
        )
    
    @staticmethod
    def extract_heuristic(soup: BeautifulSoup) -> Optional[Article]:
        """
        启发式内容提取（参考 BasicWebCrawler）
        找到包含最多段落文本的元素
        """
        # 提取标题
        title_el = soup.find('title')
        title = title_el.get_text(strip=True) if title_el else "Untitled"
        
        # 排除导航等元素
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 
                                   'header', '.sidebar', '.advertisement']):
            if hasattr(tag, 'decompose'):
                tag.decompose()
        
        # 找到最佳内容容器
        candidates = []
        for tag in ['article', 'main', 'section', 'div']:
            for elem in soup.find_all(tag):
                # 排除导航、侧边栏等
                elem_class = ' '.join(elem.get('class', [])).lower()
                elem_id = (elem.get('id') or '').lower()
                
                exclude_keywords = ['nav', 'sidebar', 'footer', 'header', 
                                    'menu', 'ad', 'banner', 'comment']
                if any(kw in elem_class or kw in elem_id for kw in exclude_keywords):
                    continue
                
                text = elem.get_text(strip=True)
                text_len = len(text)
                
                if text_len > 200:
                    score = text_len
                    # 有标题加分
                    if elem.find(['h1', 'h2', 'h3']):
                        score += 1000
                    # 有段落加分
                    p_count = len(elem.find_all('p'))
                    score += p_count * 50
                    
                    candidates.append((elem, score, text_len))
        
        if not candidates:
            return None
        
        # 选择得分最高的
        best_elem = max(candidates, key=lambda x: x[1])[0]
        content = best_elem.get_text(separator='\n', strip=True)
        
        return Article(
            title=title,
            content=content,
            html_content=str(best_elem),
        )
    
    @classmethod
    def extract(cls, html: str, url: str = "", config: dict = None) -> Article:
        """
        智能提取：依次尝试多种方法
        1. readabilipy（最智能）
        2. CSS 选择器（网站特定）
        3. 启发式算法（兜底）
        """
        soup = BeautifulSoup(html, 'html.parser')
        config = config or FINANCE_SITE_CONFIGS.get('default', {})
        
        # 方法 1: readabilipy
        article = cls.extract_with_readability(html)
        if article and article.quality_score > 0.5:
            article.engine_used = "readability"
            return article
        
        # 方法 2: CSS 选择器
        article = cls.extract_with_selectors(soup, config)
        if article:
            article.engine_used = "selectors"
            return article
        
        # 方法 3: 启发式
        article = cls.extract_heuristic(soup)
        if article:
            article.engine_used = "heuristic"
            return article
        
        # 兜底：返回整个 body
        body = soup.find('body')
        return Article(
            title=soup.title.string if soup.title else "Untitled",
            content=body.get_text(separator='\n', strip=True) if body else "",
            html_content=str(body) if body else "",
            engine_used="fallback",
        )


# ============ 爬取引擎 ============

class JinaReaderEngine:
    """
    Jina Reader API 引擎（参考 deer-flow）
    https://jina.ai/reader
    """
    
    API_URL = "https://r.jina.ai/"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("JINA_API_KEY")
    
    def crawl(self, url: str, return_format: str = "html") -> Optional[str]:
        """爬取 URL"""
        headers = {
            "Content-Type": "application/json",
            "X-Return-Format": return_format,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            response = requests.post(
                self.API_URL,
                headers=headers,
                json={"url": url},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Jina API error: {response.status_code}")
                return None
            
            return response.text
        except Exception as e:
            logger.error(f"Jina crawl failed: {e}")
            return None


class PlaywrightEngine:
    """
    Playwright 浏览器引擎（参考 BasicWebCrawler）
    支持 JS 渲染
    """
    
    def __init__(self, headless: bool = True):
        self.headless = headless
    
    def crawl(self, url: str, wait_selectors: List[str] = None, 
              timeout_ms: int = 15000) -> Optional[str]:
        """使用 Playwright 爬取"""
        if sync_playwright is None:
            logger.warning("Playwright not installed")
            return None
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=['--disable-blink-features=AutomationControlled']
                )
                
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                               'AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                )
                
                # 反检测
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                page = context.new_page()
                page.goto(url, wait_until='networkidle', timeout=timeout_ms)
                
                # 等待选择器
                if wait_selectors:
                    for sel in wait_selectors:
                        try:
                            page.wait_for_selector(sel, timeout=5000)
                            break
                        except Exception:
                            continue
                
                # 等待内容稳定
                page.wait_for_timeout(1000)
                
                content = page.content()
                context.close()
                browser.close()
                
                return content
                
        except Exception as e:
            logger.error(f"Playwright crawl failed: {e}")
            return None


class RequestsEngine:
    """
    基础 Requests 引擎
    """
    
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def crawl(self, url: str, headers: dict = None, cookies: dict = None) -> Optional[str]:
        """爬取 URL"""
        try:
            response = self.session.get(
                url,
                headers=headers,
                cookies=cookies,
                timeout=self.timeout
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return response.text
        except Exception as e:
            logger.error(f"Requests crawl failed: {e}")
            raise


# ============ 缓存 ============

class CrawlCache:
    """
    爬取缓存（参考 BasicWebCrawler）
    """
    
    def __init__(self, cache_dir: str = ".crawl_cache", ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600
    
    def _key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()
    
    def get(self, url: str) -> Optional[str]:
        """获取缓存"""
        key = self._key(url)
        cache_file = self.cache_dir / f"{key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            data = json.loads(cache_file.read_text(encoding='utf-8'))
            cached_time = datetime.fromisoformat(data['time'])
            
            if (datetime.utcnow() - cached_time).total_seconds() > self.ttl_seconds:
                cache_file.unlink()  # 过期删除
                return None
            
            return data['html']
        except Exception:
            return None
    
    def set(self, url: str, html: str):
        """设置缓存"""
        key = self._key(url)
        cache_file = self.cache_dir / f"{key}.json"
        
        try:
            data = {
                'url': url,
                'time': datetime.utcnow().isoformat(),
                'html': html,
            }
            cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")


# ============ 主爬虫类 ============

class EnhancedCrawler:
    """
    增强版爬虫
    自动选择最佳引擎，智能提取内容
    """
    
    def __init__(
        self,
        use_cache: bool = True,
        cache_ttl_hours: int = 24,
        jina_api_key: Optional[str] = None,
        default_engine: Literal['requests', 'playwright', 'jina'] = 'requests'
    ):
        self.use_cache = use_cache
        self.cache = CrawlCache(ttl_hours=cache_ttl_hours) if use_cache else None
        
        # 初始化引擎
        self.requests_engine = RequestsEngine()
        self.playwright_engine = PlaywrightEngine()
        self.jina_engine = JinaReaderEngine(api_key=jina_api_key)
        
        self.default_engine = default_engine
    
    def _get_site_config(self, url: str) -> dict:
        """获取网站配置"""
        domain = urlparse(url).netloc
        
        for site_domain, config in FINANCE_SITE_CONFIGS.items():
            if site_domain in domain:
                return config
        
        return FINANCE_SITE_CONFIGS['default']
    
    def _evaluate_quality(self, article: Article) -> float:
        """
        评估内容质量
        返回 0-1 的分数
        """
        score = 0.0
        
        # 内容长度
        content_len = len(article.content)
        if content_len > 500:
            score += 0.3
        elif content_len > 200:
            score += 0.2
        elif content_len > 100:
            score += 0.1
        
        # 有标题
        if article.title and article.title != "Untitled":
            score += 0.2
        
        # 中文内容比例（财经新闻应该主要是中文）
        chinese_pattern = re.compile(r'[\u4e00-\u9fa5]')
        chinese_count = len(chinese_pattern.findall(article.content))
        if content_len > 0:
            chinese_ratio = chinese_count / content_len
            if chinese_ratio > 0.5:
                score += 0.3
            elif chinese_ratio > 0.3:
                score += 0.2
        
        # 段落结构
        paragraph_count = article.content.count('\n')
        if paragraph_count > 5:
            score += 0.2
        elif paragraph_count > 2:
            score += 0.1
        
        return min(score, 1.0)
    
    def crawl(
        self,
        url: str,
        engine: Optional[Literal['requests', 'playwright', 'jina', 'auto']] = None,
        force_refresh: bool = False
    ) -> Article:
        """
        爬取单个 URL
        
        Args:
            url: 目标 URL
            engine: 爬取引擎 ('requests', 'playwright', 'jina', 'auto')
            force_refresh: 是否强制刷新缓存
            
        Returns:
            Article 对象
        """
        # 检查缓存
        if self.use_cache and not force_refresh:
            cached_html = self.cache.get(url)
            if cached_html:
                logger.info(f"Using cached content for {url}")
                article = ContentExtractor.extract(cached_html, url)
                article.url = url
                article.quality_score = self._evaluate_quality(article)
                return article
        
        # 获取网站配置
        config = self._get_site_config(url)
        engine = engine or self.default_engine
        
        html = None
        used_engine = engine
        
        # 自动选择引擎
        if engine == 'auto':
            if config.get('needs_js'):
                engine = 'playwright'
            else:
                engine = 'requests'
        
        # 爬取
        if engine == 'requests':
            html = self.requests_engine.crawl(
                url,
                headers=config.get('headers'),
                cookies=config.get('cookies')
            )
            used_engine = 'requests'
            
        elif engine == 'playwright':
            html = self.playwright_engine.crawl(
                url,
                wait_selectors=config.get('wait_selectors')
            )
            used_engine = 'playwright'
            
        elif engine == 'jina':
            html = self.jina_engine.crawl(url)
            used_engine = 'jina'
        
        # 如果主引擎失败，尝试备用引擎
        if not html or len(html) < 500:
            logger.warning(f"Primary engine failed, trying fallback...")
            
            if used_engine != 'jina' and self.jina_engine.api_key:
                html = self.jina_engine.crawl(url)
                used_engine = 'jina'
            
            if not html and used_engine != 'playwright' and sync_playwright:
                html = self.playwright_engine.crawl(url)
                used_engine = 'playwright'
        
        if not html:
            logger.error(f"All engines failed for {url}")
            return Article(
                title="Crawl Failed",
                content=f"Failed to crawl {url}",
                url=url,
                engine_used="none",
                quality_score=0.0
            )
        
        # 缓存
        if self.use_cache:
            self.cache.set(url, html)
        
        # 提取内容
        article = ContentExtractor.extract(html, url, config)
        article.url = url
        article.source = urlparse(url).netloc
        article.engine_used = used_engine
        article.quality_score = self._evaluate_quality(article)
        
        # 质量检查：如果质量太低且没用过 Jina，尝试用 Jina
        if article.quality_score < 0.3 and used_engine != 'jina' and self.jina_engine.api_key:
            logger.info(f"Low quality ({article.quality_score:.2f}), retrying with Jina...")
            jina_html = self.jina_engine.crawl(url)
            if jina_html:
                jina_article = ContentExtractor.extract(jina_html, url, config)
                jina_article.quality_score = self._evaluate_quality(jina_article)
                
                if jina_article.quality_score > article.quality_score:
                    article = jina_article
                    article.engine_used = 'jina'
        
        return article
    
    def crawl_batch(
        self,
        urls: List[str],
        engine: Optional[str] = None,
        delay: float = 1.0
    ) -> List[Article]:
        """
        批量爬取
        
        Args:
            urls: URL 列表
            engine: 爬取引擎
            delay: 请求间隔（秒）
            
        Returns:
            Article 列表
        """
        articles = []
        
        for i, url in enumerate(urls):
            logger.info(f"Crawling {i+1}/{len(urls)}: {url}")
            
            try:
                article = self.crawl(url, engine=engine)
                articles.append(article)
            except Exception as e:
                logger.error(f"Failed to crawl {url}: {e}")
                articles.append(Article(
                    title="Crawl Failed",
                    content=str(e),
                    url=url,
                    quality_score=0.0
                ))
            
            if delay > 0 and i < len(urls) - 1:
                time.sleep(delay)
        
        return articles


# ============ 便捷函数 ============

# 全局爬虫实例
_crawler: Optional[EnhancedCrawler] = None


def get_crawler() -> EnhancedCrawler:
    """获取全局爬虫实例"""
    global _crawler
    if _crawler is None:
        _crawler = EnhancedCrawler()
    return _crawler


def crawl_url(url: str, engine: str = 'auto') -> Article:
    """便捷函数：爬取单个 URL"""
    return get_crawler().crawl(url, engine=engine)


def crawl_urls(urls: List[str], engine: str = 'auto') -> List[Article]:
    """便捷函数：批量爬取"""
    return get_crawler().crawl_batch(urls, engine=engine)


# ============ 测试 ============

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 测试爬取
    test_urls = [
        "https://finance.sina.com.cn/roll/c/56592.shtml",
    ]
    
    crawler = EnhancedCrawler(use_cache=True)
    
    for url in test_urls:
        print(f"\n{'='*60}")
        print(f"Crawling: {url}")
        
        article = crawler.crawl(url, engine='auto')
        
        print(f"Title: {article.title}")
        print(f"Engine: {article.engine_used}")
        print(f"Quality: {article.quality_score:.2f}")
        print(f"Content length: {len(article.content)}")
        print(f"Preview: {article.content[:200]}...")

