"""
调试 API - 用于测试爬虫和内容提取
"""
import re
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
router = APIRouter()


class CrawlRequest(BaseModel):
    url: str
    return_html: bool = True  # 是否返回原始 HTML


class CrawlResponse(BaseModel):
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    content_length: int = 0
    html_length: int = 0
    raw_html: Optional[str] = None  # 原始 HTML（可选）
    debug_info: dict = {}


def extract_chinese_ratio(text: str) -> float:
    """计算中文字符比例"""
    pattern = re.compile(r'[\u4e00-\u9fa5]+')
    chinese_chars = pattern.findall(text)
    chinese_count = sum(len(chars) for chars in chinese_chars)
    total_count = len(text)
    return chinese_count / total_count if total_count > 0 else 0


def clean_text(text: str) -> str:
    """清理文本"""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\u3000', ' ')
    text = ' '.join(text.split())
    return text.strip()


def is_noise_text(text: str) -> bool:
    """判断是否为噪音文本"""
    noise_patterns = [
        r'^责任编辑',
        r'^编辑[:：]',
        r'^来源[:：]',
        r'^声明[:：]',
        r'^免责声明',
        r'^版权',
        r'^copyright',
        r'^点击进入',
        r'^相关阅读',
        r'^延伸阅读',
        r'登录新浪财经APP',
        r'搜索【信披】',
        r'缩小字体',
        r'放大字体',
        r'收藏',
        r'微博',
        r'微信',
        r'分享',
        r'腾讯QQ',
    ]
    text_lower = text.lower().strip()
    for pattern in noise_patterns:
        if re.search(pattern, text_lower, re.I):
            return True
    return False


def extract_content_from_html(html: str, url: str) -> tuple[str, str, dict]:
    """
    从 HTML 中提取内容
    返回: (title, content, debug_info)
    """
    soup = BeautifulSoup(html, 'lxml')
    debug_info = {
        "selectors_tried": [],
        "selector_matched": None,
        "total_lines_raw": 0,
        "lines_kept": 0,
        "lines_filtered": 0,
    }
    
    # 提取标题
    title = ""
    title_tag = soup.find('h1', class_='main-title') or soup.find('h1') or soup.find('title')
    if title_tag:
        title = title_tag.get_text().strip()
        title = re.sub(r'[-_].*?(新浪|财经|网)', '', title).strip()
    
    # 内容选择器（按优先级）
    content_selectors = [
        {'id': 'artibody'},
        {'class': 'article-content'},
        {'class': 'article'},
        {'id': 'article'},
        {'class': 'content'},
        {'class': 'news-content'},
    ]
    
    for selector in content_selectors:
        debug_info["selectors_tried"].append(str(selector))
        content_div = soup.find(['div', 'article'], selector)
        
        if content_div:
            debug_info["selector_matched"] = str(selector)
            
            # 移除噪音元素
            for tag in content_div.find_all(['script', 'style', 'iframe', 'ins', 'select', 'input', 'button', 'form']):
                tag.decompose()
            for ad in content_div.find_all(class_=re.compile(r'ad|banner|share|otherContent|recommend|app-guide', re.I)):
                ad.decompose()
            
            # 获取全文
            full_text = content_div.get_text(separator='\n', strip=True)
            lines = full_text.split('\n')
            debug_info["total_lines_raw"] = len(lines)
            
            article_parts = []
            for line in lines:
                line = line.strip()
                if not line or len(line) < 2:
                    continue
                
                chinese_ratio = extract_chinese_ratio(line)
                if chinese_ratio > 0.05 or len(line) > 20:
                    clean_line = clean_text(line)
                    if clean_line and not is_noise_text(clean_line):
                        article_parts.append(clean_line)
                        debug_info["lines_kept"] += 1
                    else:
                        debug_info["lines_filtered"] += 1
                else:
                    debug_info["lines_filtered"] += 1
            
            content = '\n'.join(article_parts)
            return title, content, debug_info
    
    debug_info["selector_matched"] = "fallback (body)"
    # 后备：直接取 body
    body = soup.find('body')
    if body:
        content = body.get_text(separator='\n', strip=True)
        return title, content[:5000], debug_info  # 限制长度
    
    return title, "", debug_info


@router.post("/crawl", response_model=CrawlResponse)
async def debug_crawl(request: CrawlRequest):
    """
    实时爬取指定 URL 并返回内容（用于调试）
    
    - **url**: 要爬取的新闻 URL
    - **return_html**: 是否返回原始 HTML（默认 True）
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(request.url, headers=headers, timeout=30)
        response.encoding = 'utf-8'
        html = response.text
        
        title, content, debug_info = extract_content_from_html(html, request.url)
        
        return CrawlResponse(
            url=request.url,
            title=title,
            content=content,
            content_length=len(content),
            html_length=len(html),
            raw_html=html if request.return_html else None,
            debug_info=debug_info,
        )
        
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"爬取失败: {str(e)}")
    except Exception as e:
        logger.error(f"Debug crawl error: {e}")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@router.get("/test-sina")
async def test_sina_crawl():
    """
    测试新浪财经爬取（使用固定 URL）
    """
    test_url = "https://finance.sina.com.cn/jjxw/2024-12-28/doc-ineayfsz5142013.shtml"
    request = CrawlRequest(url=test_url, return_html=False)
    return await debug_crawl(request)

