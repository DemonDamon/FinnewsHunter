"""
交互式网页爬虫
使用 requests + BeautifulSoup 进行网页爬取
特别用于搜索结果补充，当 BochaAI 结果不足时使用

注意：主要搜索引擎（Bing、百度）都有反爬机制，本模块已做相应优化：
1. 模拟真实浏览器请求头
2. 检测验证页面并自动降级
3. 多引擎轮换备选
"""
import logging
import re
import time
import random
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 更完善的 User-Agent，模拟最新的 Chrome 浏览器
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
]

# 验证页面关键词（用于检测被拦截）
CAPTCHA_KEYWORDS = [
    '确认您是真人', '人机验证', 'captcha', 'verify you are human',
    '验证码', '请完成验证', '安全验证', '异常访问', '请输入验证码',
    '最后一步', '请解决以下难题'
]


class InteractiveCrawler:
    """交互式网页爬虫（纯 requests 实现）"""
    
    def __init__(self, timeout: int = 15):
        """
        初始化爬虫
        
        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        self.session = requests.Session()
        self._user_agent = random.choice(USER_AGENTS)
        # 更完善的请求头，模拟真实浏览器
        self.session.headers.update({
            'User-Agent': self._user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        })
    
    def _is_captcha_page(self, html_content: str, soup: BeautifulSoup = None) -> bool:
        """
        检测页面是否为验证码/人机验证页面
        
        Args:
            html_content: HTML 原始内容
            soup: 已解析的 BeautifulSoup 对象
            
        Returns:
            True 如果是验证页面
        """
        text_to_check = html_content.lower()
        if soup:
            text_to_check = soup.get_text().lower()
        
        for keyword in CAPTCHA_KEYWORDS:
            if keyword.lower() in text_to_check:
                return True
        return False
    
    def search_on_bing(
        self,
        query: str,
        num_results: int = 10
    ) -> List[Dict[str, str]]:
        """
        在 Bing 上搜索并获取结果
        
        Args:
            query: 搜索关键词
            num_results: 获取的结果数量
            
        Returns:
            搜索结果列表 [{"url": "...", "title": "...", "snippet": "..."}]
        """
        results = []
        
        try:
            # 使用国际版 Bing，中国版有更严格的反爬
            search_url = f"https://www.bing.com/search?q={quote_plus(query)}&count={num_results}"
            
            logger.info(f"🔍 Bing 搜索: {query}")
            logger.debug(f"搜索URL: {search_url}")
            
            response = self.session.get(search_url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ========== 检测验证码页面 ==========
            if self._is_captcha_page(response.text, soup):
                logger.warning("⚠️ Bing 触发人机验证，跳过此引擎")
                return []  # 返回空，让调用者使用其他引擎
            
            # ========== 调试：打印找到的元素 ==========
            # 尝试多种选择器
            b_algo_items = soup.select('.b_algo')
            logger.info(f"📊 Bing HTML解析: .b_algo={len(b_algo_items)}个")
            
            # 如果 .b_algo 没找到，尝试其他选择器
            if not b_algo_items:
                # 尝试查找所有包含链接的 li 元素
                li_items = soup.select('#b_results > li')
                logger.info(f"📊 尝试 #b_results > li: {len(li_items)}个")
                
                # 打印页面中所有链接供调试
                all_links = soup.select('a[href^="http"]')
                logger.info(f"📊 页面总链接数: {len(all_links)}个")
                
                # 打印前10个链接
                for i, link in enumerate(all_links[:15]):
                    href = link.get('href', '')
                    text = link.get_text(strip=True)[:50]
                    # 过滤掉 Bing 内部链接
                    if 'bing.com' not in href and 'microsoft.com' not in href:
                        logger.info(f"  链接{i+1}: {text} -> {href[:80]}")
            
            # ========== 提取搜索结果 ==========
            # 方法1: 标准 .b_algo 选择器
            for result in b_algo_items[:num_results]:
                try:
                    # 提取标题和链接
                    title_elem = result.select_one('h2 a')
                    if not title_elem:
                        title_elem = result.select_one('a')  # 备选
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    
                    # 提取摘要
                    snippet_elem = result.select_one('.b_caption p, p')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                    
                    if url and title and 'bing.com' not in url:
                        results.append({
                            "url": url,
                            "title": title,
                            "snippet": snippet[:300],
                            "source": "bing"
                        })
                        logger.debug(f"  ✅ 提取: {title[:40]} -> {url[:60]}")
                        
                except Exception as e:
                    logger.debug(f"解析 Bing 结果失败: {e}")
                    continue
            
            # 方法2: 如果 .b_algo 没有结果，可能是验证页面的残留链接，不再使用备选提取
            if not results and b_algo_items:
                logger.info("⚠️ Bing 无有效结果")
            
            logger.info(f"✅ Bing 搜索完成，获得 {len(results)} 条结果")
            
        except requests.exceptions.Timeout:
            logger.warning(f"⚠️ Bing 搜索超时: {query}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ Bing 搜索请求失败: {e}")
        except Exception as e:
            logger.error(f"❌ Bing 搜索失败: {e}")
        
        return results
    
    def search_on_baidu(
        self,
        query: str,
        num_results: int = 10
    ) -> List[Dict[str, str]]:
        """
        在百度上搜索并获取结果（百度对简单爬虫相对友好）
        
        Args:
            query: 搜索关键词
            num_results: 获取的结果数量
            
        Returns:
            搜索结果列表
        """
        results = []
        
        try:
            # 百度搜索 URL
            search_url = f"https://www.baidu.com/s?wd={quote_plus(query)}&rn={num_results}"
            
            logger.info(f"🔍 百度搜索: {query}")
            logger.debug(f"搜索URL: {search_url}")
            
            # 百度需要特定的请求头
            headers = {
                'User-Agent': self._user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Referer': 'https://www.baidu.com/',
                'Connection': 'keep-alive',
            }
            
            response = self.session.get(search_url, headers=headers, timeout=self.timeout)
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 检测验证码
            if self._is_captcha_page(response.text, soup):
                logger.warning("⚠️ 百度触发验证，跳过此引擎")
                return []
            
            # 百度搜索结果选择器（多种尝试）
            result_items = soup.select('.result.c-container, .c-container, div[class*="result"]')
            logger.info(f"📊 百度HTML解析: 结果容器={len(result_items)}个")
            
            for result in result_items[:num_results]:
                try:
                    # 提取标题和链接
                    title_elem = result.select_one('h3 a, .t a, a[href]')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    
                    # 百度使用跳转链接，需要提取真实URL
                    # 但通常跳转链接也能用
                    
                    # 提取摘要
                    snippet_elem = result.select_one('.c-abstract, .c-span-last, .content-right_8Zs40')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                    
                    if url and title and 'baidu.com' not in url:
                        results.append({
                            "url": url,
                            "title": title,
                            "snippet": snippet[:300],
                            "source": "baidu"
                        })
                        logger.debug(f"  ✅ 提取: {title[:40]}")
                        
                except Exception as e:
                    logger.debug(f"解析百度结果失败: {e}")
                    continue
            
            # 备选方法：从所有标题链接提取
            if not results:
                logger.info("⚠️ 百度标准选择器无结果，尝试提取 h3 链接...")
                h3_links = soup.select('h3 a')
                for link in h3_links[:num_results]:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    if not href or not text or len(text) < 3:
                        continue
                    if href in [r['url'] for r in results]:
                        continue
                    
                    results.append({
                        "url": href,
                        "title": text[:100],
                        "snippet": "",
                        "source": "baidu"
                    })
                    
                    if len(results) >= num_results:
                        break
            
            logger.info(f"✅ 百度搜索完成，获得 {len(results)} 条结果")
            
        except Exception as e:
            logger.warning(f"⚠️ 百度搜索失败: {e}")
        
        return results
    
    def search_on_baidu_news(
        self,
        query: str,
        num_results: int = 10
    ) -> List[Dict[str, str]]:
        """
        在百度新闻搜索（news.baidu.com）获取新闻结果
        
        使用 news.baidu.com 入口，返回的 URL 是真实的第三方新闻链接，
        不是百度跳转链接，避免乱码问题。
        
        Args:
            query: 搜索关键词
            num_results: 获取的结果数量
            
        Returns:
            搜索结果列表
        """
        results = []
        
        try:
            # 使用百度新闻入口（news.baidu.com），返回真实的第三方 URL
            search_url = f"https://news.baidu.com/ns?word={quote_plus(query)}&tn=news&from=news&cl=2&rn={num_results}&ct=1"
            
            logger.info(f"🔍 百度新闻搜索: {query}")
            logger.debug(f"搜索URL: {search_url}")
            
            # 百度需要特定的请求头
            headers = {
                'User-Agent': self._user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Referer': 'https://news.baidu.com/',
                'Connection': 'keep-alive',
            }
            
            response = self.session.get(search_url, headers=headers, timeout=self.timeout, allow_redirects=True)
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 检测验证码
            if self._is_captcha_page(response.text, soup):
                logger.warning("⚠️ 百度新闻触发验证，跳过")
                return []
            
            # 百度新闻搜索结果选择器
            # 新闻标题在 h3 > a 中，链接是真实的第三方 URL
            news_h3_links = soup.select('h3 a[href^="http"]')
            logger.info(f"📊 百度新闻HTML解析: h3链接={len(news_h3_links)}个")
            
            for link in news_h3_links[:num_results * 2]:  # 多取一些，后面过滤
                try:
                    url = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # 清理标题（去掉"标题："前缀）
                    if title.startswith('标题：'):
                        title = title[3:]
                    
                    # 过滤无效结果
                    if not url or not title or len(title) < 5:
                        continue
                    # 过滤百度内部链接（但保留百家号 baijiahao.baidu.com）
                    if 'baidu.com' in url and 'baijiahao.baidu.com' not in url:
                        continue
                    if url in [r['url'] for r in results]:
                        continue  # 去重
                    
                    # 尝试找到父容器获取摘要
                    parent = link.find_parent(['div', 'li'])
                    snippet = ''
                    news_source = ''
                    publish_time = ''
                    
                    if parent:
                        # 提取摘要（通常在 generic 或 p 元素中）
                        snippet_elem = parent.select_one('[class*="summary"], [class*="abstract"], p')
                        if snippet_elem:
                            snippet = snippet_elem.get_text(strip=True)[:300]
                        
                        # 提取来源（通常在包含"来源"的链接中）
                        source_links = parent.select('a')
                        for src_link in source_links:
                            src_text = src_link.get_text(strip=True)
                            if src_text and src_text != title[:20] and len(src_text) < 20:
                                # 可能是来源（如"同花顺财经"、"新浪财经"）
                                if '新闻来源' in (src_link.get('aria-label', '') or ''):
                                    news_source = src_text
                                    break
                                elif not news_source and not src_text.startswith('标题'):
                                    news_source = src_text
                    
                    results.append({
                        "url": url,
                        "title": title,
                        "snippet": snippet,
                        "source": "baidu_news",
                        "news_source": news_source  # 新闻来源（如"同花顺财经"）
                    })
                    logger.debug(f"  ✅ 新闻: {title[:40]} | {news_source}")
                    
                    if len(results) >= num_results:
                        break
                        
                except Exception as e:
                    logger.debug(f"解析百度新闻结果失败: {e}")
                    continue
            
            logger.info(f"✅ 百度新闻搜索完成，获得 {len(results)} 条新闻")
            
        except Exception as e:
            logger.warning(f"⚠️ 百度新闻搜索失败: {e}")
        
        return results
    
    def search_on_sogou(
        self,
        query: str,
        num_results: int = 10
    ) -> List[Dict[str, str]]:
        """
        在搜狗上搜索并获取结果（备用搜索引擎）
        
        Args:
            query: 搜索关键词
            num_results: 获取的结果数量
            
        Returns:
            搜索结果列表
        """
        results = []
        
        try:
            # 构建搜狗搜索 URL
            search_url = f"https://www.sogou.com/web?query={quote_plus(query)}"
            
            logger.info(f"🔍 搜狗搜索: {query}")
            logger.debug(f"搜索URL: {search_url}")
            
            response = self.session.get(search_url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 检测验证码
            if self._is_captcha_page(response.text, soup):
                logger.warning("⚠️ 搜狗触发验证，跳过此引擎")
                return []
            
            # ========== 调试：打印找到的元素 ==========
            vrwrap_items = soup.select('.vrwrap, .rb, .results .vrwrap')
            logger.info(f"📊 搜狗HTML解析: .vrwrap/.rb={len(vrwrap_items)}个")
            
            # 搜狗搜索结果选择器
            for result in vrwrap_items[:num_results]:
                try:
                    title_elem = result.select_one('h3 a, .vr-title a, a[href]')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    
                    snippet_elem = result.select_one('.str_info, .str-text, p, .txt-info')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                    
                    if url and title and 'sogou.com' not in url:
                        results.append({
                            "url": url,
                            "title": title,
                            "snippet": snippet[:300],
                            "source": "sogou"
                        })
                        logger.debug(f"  ✅ 提取: {title[:40]} -> {url[:60]}")
                        
                except Exception as e:
                    logger.debug(f"解析搜狗结果失败: {e}")
                    continue
            
            # 备选方法：从页面链接提取
            if not results:
                logger.info("⚠️ 搜狗标准选择器无结果，尝试从页面链接提取...")
                all_links = soup.select('a[href^="http"]')
                for link in all_links[:num_results * 3]:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    if not href or not text or len(text) < 5:
                        continue
                    if 'sogou.com' in href:
                        continue
                    if href in [r['url'] for r in results]:
                        continue
                    
                    results.append({
                        "url": href,
                        "title": text[:100],
                        "snippet": "",
                        "source": "sogou"
                    })
                    
                    if len(results) >= num_results:
                        break
            
            logger.info(f"✅ 搜狗搜索完成，获得 {len(results)} 条结果")
            
        except Exception as e:
            logger.warning(f"⚠️ 搜狗搜索失败: {e}")
        
        return results
    
    def search_on_360(
        self,
        query: str,
        num_results: int = 10
    ) -> List[Dict[str, str]]:
        """
        在 360 搜索上搜索并获取结果
        
        Args:
            query: 搜索关键词
            num_results: 获取的结果数量
            
        Returns:
            搜索结果列表
        """
        results = []
        
        try:
            # 构建 360 搜索 URL
            search_url = f"https://www.so.com/s?q={quote_plus(query)}"
            
            logger.info(f"🔍 360搜索: {query}")
            logger.debug(f"搜索URL: {search_url}")
            
            response = self.session.get(search_url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 检测验证码
            if self._is_captcha_page(response.text, soup):
                logger.warning("⚠️ 360触发验证，跳过此引擎")
                return []
            
            # ========== 调试：打印找到的元素 ==========
            res_items = soup.select('.res-list, .result, li.res-list')
            logger.info(f"📊 360 HTML解析: .res-list/.result={len(res_items)}个")
            
            # 360 搜索结果选择器
            for result in res_items[:num_results]:
                try:
                    title_elem = result.select_one('h3 a, .res-title a, a[href]')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    
                    snippet_elem = result.select_one('.res-desc, p.res-summary, p, .res-comm-con')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                    
                    if url and title and 'so.com' not in url and '360.cn' not in url:
                        results.append({
                            "url": url,
                            "title": title,
                            "snippet": snippet[:300],
                            "source": "360"
                        })
                        logger.debug(f"  ✅ 提取: {title[:40]} -> {url[:60]}")
                        
                except Exception as e:
                    logger.debug(f"解析 360 结果失败: {e}")
                    continue
            
            # 备选方法：从页面链接提取
            if not results:
                logger.info("⚠️ 360 标准选择器无结果，尝试从页面链接提取...")
                all_links = soup.select('a[href^="http"]')
                for link in all_links[:num_results * 3]:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    if not href or not text or len(text) < 5:
                        continue
                    if 'so.com' in href or '360.cn' in href:
                        continue
                    if href in [r['url'] for r in results]:
                        continue
                    
                    results.append({
                        "url": href,
                        "title": text[:100],
                        "snippet": "",
                        "source": "360"
                    })
                    
                    if len(results) >= num_results:
                        break
            
            logger.info(f"✅ 360搜索完成，获得 {len(results)} 条结果")
            
        except Exception as e:
            logger.warning(f"⚠️ 360搜索失败: {e}")
        
        return results
    
    def interactive_search(
        self,
        query: str,
        engines: List[str] = None,
        num_results: int = 10,
        search_type: str = "news",  # 新增参数：news（新闻）或 web（网页）
        **kwargs  # 兼容旧接口
    ) -> List[Dict[str, str]]:
        """
        使用多个搜索引擎进行搜索
        
        Args:
            query: 搜索关键词
            engines: 搜索引擎列表 ['baidu_news', 'baidu', 'sogou', '360', 'bing']
            num_results: 每个引擎的结果数量
            search_type: 搜索类型 'news'（新闻优先）或 'web'（网页）
            
        Returns:
            合并的搜索结果
        """
        if engines is None:
            if search_type == "news":
                # 新闻搜索：优先使用百度资讯
                engines = ["baidu_news", "sogou"]
            else:
                # 普通网页搜索
                engines = ["baidu", "sogou"]
        
        all_results = []
        engines_tried = []
        
        for engine in engines:
            try:
                engine_lower = engine.lower()
                if engine_lower == "baidu_news":
                    results = self.search_on_baidu_news(query, num_results)
                elif engine_lower == "baidu":
                    results = self.search_on_baidu(query, num_results)
                elif engine_lower == "bing":
                    results = self.search_on_bing(query, num_results)
                elif engine_lower == "sogou":
                    results = self.search_on_sogou(query, num_results)
                elif engine_lower == "360":
                    results = self.search_on_360(query, num_results)
                else:
                    logger.warning(f"⚠️ 不支持的搜索引擎: {engine}")
                    continue
                
                if results:
                    all_results.extend(results)
                    engines_tried.append(engine_lower)
                    logger.info(f"✅ {engine} 返回 {len(results)} 条结果")
                else:
                    logger.info(f"⚠️ {engine} 无结果或被拦截")
                
                # 搜索间隔，避免被封
                if len(engines) > 1:
                    time.sleep(random.uniform(0.8, 1.5))
                    
            except Exception as e:
                logger.error(f"❌ 使用 {engine} 搜索失败: {e}")
                continue
        
        # 如果所有引擎都失败了，尝试备用引擎
        if not all_results:
            backup_engines = ["baidu_news", "360", "baidu", "sogou"]
            for backup in backup_engines:
                if backup not in [e.lower() for e in engines]:
                    logger.info(f"🔄 尝试备用引擎: {backup}")
                    try:
                        if backup == "baidu_news":
                            results = self.search_on_baidu_news(query, num_results)
                        elif backup == "360":
                            results = self.search_on_360(query, num_results)
                        elif backup == "baidu":
                            results = self.search_on_baidu(query, num_results)
                        elif backup == "sogou":
                            results = self.search_on_sogou(query, num_results)
                        
                        if results:
                            all_results.extend(results)
                            engines_tried.append(backup)
                            logger.info(f"✅ 备用引擎 {backup} 返回 {len(results)} 条结果")
                            break
                    except Exception as e:
                        logger.warning(f"备用引擎 {backup} 也失败: {e}")
                        continue
        
        # 去重
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique_results.append(r)
        
        logger.info(f"交互式搜索完成: {len(all_results)} -> {len(unique_results)} (去重后), 使用引擎: {engines_tried}")
        return unique_results
    
    def crawl_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        爬取单个页面内容
        
        Args:
            url: 页面 URL
            
        Returns:
            {"url": "...", "title": "...", "content": "...", "text": "...", "html": "..."} 或 None
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.encoding = response.apparent_encoding or 'utf-8'
            
            # 保存原始 HTML（清理 NUL 字符）
            raw_html = response.text.replace('\x00', '').replace('\0', '')
            
            soup = BeautifulSoup(raw_html, 'html.parser')
            
            # 获取标题（在移除元素之前）
            title = ''
            title_elem = soup.find('title')
            if title_elem:
                title = title_elem.get_text(strip=True)
            
            # 尝试获取 h1 作为更好的标题
            h1_elem = soup.find('h1')
            if h1_elem:
                h1_text = h1_elem.get_text(strip=True)
                if h1_text and len(h1_text) > 5:
                    title = h1_text
            
            # 移除无关元素（用于提取正文）
            for elem in soup.select('script, style, iframe, nav, footer, header, aside, .ad, .advertisement, .comment, .sidebar'):
                elem.decompose()
            
            # 获取主要内容
            # 优先选择 article, main, .content 等
            main_content = None
            content_selectors = [
                'article', 'main', '.content', '.post-content', '.article-content', 
                '#content', '.main-content', '.news-content', '.article-body',
                '.entry-content', '.post-body', '[itemprop="articleBody"]'
            ]
            for selector in content_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            if not main_content:
                main_content = soup.find('body') or soup
            
            # 提取文本
            text_content = main_content.get_text(separator='\n', strip=True)
            
            # 清理文本
            text_content = re.sub(r'\n{3,}', '\n\n', text_content)
            # 不再截断内容，保留完整正文（数据库字段应该支持长文本）
            # text_content = text_content[:5000]  # 移除截断
            
            logger.debug(f"📄 爬取完成: {title[:40]}... | 正文{len(text_content)}字符 | HTML{len(raw_html) if raw_html else 0}字符")
            
            return {
                "url": url,
                "title": title,
                "content": text_content,  # 完整正文
                "text": text_content,  # 兼容字段
                "html": raw_html if raw_html else None  # 完整原始 HTML
            }
            
        except requests.exceptions.Timeout:
            logger.warning(f"⚠️ 爬取页面超时: {url[:60]}...")
        except Exception as e:
            logger.warning(f"⚠️ 爬取页面失败 {url[:60]}...: {e}")
        
        return None
    
    def crawl_search_results(
        self,
        search_results: List[Dict[str, str]],
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        爬取搜索结果中的页面内容
        
        Args:
            search_results: 搜索结果列表
            max_results: 最多爬取多少个页面
            
        Returns:
            爬取结果列表 [{"url": "...", "title": "...", "content": "..."}]
        """
        crawled = []
        
        for i, result in enumerate(search_results[:max_results]):
            url = result.get("url")
            if not url:
                continue
            
            logger.info(f"📄 爬取页面 {i+1}/{min(max_results, len(search_results))}: {url[:60]}...")
            
            page_data = self.crawl_page(url)
            
            if page_data and page_data.get("content"):
                page_data["snippet"] = result.get("snippet", "")
                page_data["source"] = result.get("source", "web")
                crawled.append(page_data)
                logger.debug(f"✅ 爬取成功: {page_data['title'][:50]}...")
            else:
                # 爬取失败时，使用搜索结果的摘要
                crawled.append({
                    "url": url,
                    "title": result.get("title", ""),
                    "content": result.get("snippet", ""),
                    "snippet": result.get("snippet", ""),
                    "source": result.get("source", "web")
                })
                logger.debug(f"⚠️ 使用摘要代替: {result.get('title', 'N/A')[:50]}...")
            
            # 爬取间隔
            if i < max_results - 1:
                time.sleep(random.uniform(0.3, 0.8))
        
        logger.info(f"📄 页面爬取完成: {len(crawled)} 个成功")
        return crawled


# 便捷函数
def create_interactive_crawler(headless: bool = True, **kwargs) -> InteractiveCrawler:
    """创建交互式爬虫（兼容旧接口）"""
    return InteractiveCrawler()


def search_and_crawl(
    query: str,
    engines: List[str] = None,
    max_search_results: int = 10,
    max_crawl_results: int = 5,
    **kwargs  # 兼容旧接口
) -> Dict[str, Any]:
    """
    一体化搜索和爬取函数
    
    Args:
        query: 搜索关键词
        engines: 搜索引擎列表
        max_search_results: 最多获取多少个搜索结果
        max_crawl_results: 最多爬取多少个页面
        
    Returns:
        {
            "search_results": [...],
            "crawled_results": [...],
            "total_results": int
        }
    """
    crawler = InteractiveCrawler()
    
    logger.info(f"🔍 开始搜索: {query}")
    search_results = crawler.interactive_search(
        query,
        engines=engines,
        num_results=max_search_results
    )
    
    if not search_results:
        logger.warning(f"搜索未返回结果: {query}")
        return {
            "search_results": [],
            "crawled_results": [],
            "total_results": 0
        }
    
    logger.info(f"📄 开始爬取前 {max_crawl_results} 个结果")
    crawled_results = crawler.crawl_search_results(
        search_results,
        max_results=max_crawl_results
    )
    
    return {
        "search_results": search_results,
        "crawled_results": crawled_results,
        "total_results": len(crawled_results)
    }
