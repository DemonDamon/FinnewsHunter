"""
BochaAI Web Search Tool
用于定向搜索股票相关新闻
"""
import json
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """搜索结果数据类"""
    title: str
    url: str
    snippet: str
    site_name: Optional[str] = None
    date_published: Optional[str] = None
    

class BochaAISearchTool:
    """
    BochaAI Web Search 工具
    用于搜索股票相关新闻
    """
    
    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        """
        初始化 BochaAI 搜索工具
        
        Args:
            api_key: BochaAI API Key（如果不提供，从配置中获取）
            endpoint: API 端点（默认使用配置中的端点）
        """
        self.api_key = api_key or settings.BOCHAAI_API_KEY
        self.endpoint = endpoint or settings.BOCHAAI_ENDPOINT
        
        if not self.api_key:
            logger.warning(
                "BochaAI API Key 未配置，搜索功能将不可用。\n"
                "请在 .env 文件中设置 BOCHAAI_API_KEY=your_api_key"
            )
    
    def is_available(self) -> bool:
        """检查搜索功能是否可用"""
        return bool(self.api_key)
    
    def search(
        self,
        query: str,
        freshness: str = "noLimit",
        count: int = 10,
        include_sites: Optional[str] = None,
        exclude_sites: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        执行 Web 搜索
        
        Args:
            query: 搜索查询字符串
            freshness: 时间范围（noLimit, day, week, month）
            count: 返回结果数量（1-50）
            include_sites: 限定搜索的网站（逗号分隔）
            exclude_sites: 排除的网站（逗号分隔）
            
        Returns:
            搜索结果列表
        """
        if not self.is_available():
            logger.warning("BochaAI API Key 未配置，跳过搜索")
            return []
        
        try:
            # 构建请求数据
            request_data = {
                "query": query,
                "freshness": freshness,
                "summary": False,
                "count": min(max(count, 1), 50)
            }
            
            if include_sites:
                request_data["include"] = include_sites
            if exclude_sites:
                request_data["exclude"] = exclude_sites
            
            # 创建请求
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(request_data).encode('utf-8'),
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'FinnewsHunter-BochaAI-Search/1.0'
                }
            )
            
            # 发送请求
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read().decode('utf-8')
                result = json.loads(data)
            
            # 解析结果
            results = []
            
            if 'data' in result:
                data = result['data']
                if 'webPages' in data and data['webPages'] and 'value' in data['webPages']:
                    for item in data['webPages']['value']:
                        search_result = SearchResult(
                            title=item.get('name', '无标题'),
                            url=item.get('url', ''),
                            snippet=item.get('snippet', ''),
                            site_name=item.get('siteName', ''),
                            date_published=item.get('datePublished', '')
                        )
                        results.append(search_result)
            
            logger.info(f"BochaAI 搜索完成: query='{query}', 结果数={len(results)}")
            return results
            
        except urllib.error.HTTPError as e:
            error_msg = f"BochaAI API HTTP 错误: {e.code} - {e.reason}"
            if e.code == 401:
                error_msg += " (请检查 BOCHAAI_API_KEY 是否正确)"
            elif e.code == 429:
                error_msg += " (请求过于频繁)"
            logger.error(error_msg)
            return []
            
        except urllib.error.URLError as e:
            logger.error(f"BochaAI 网络错误: {e.reason}")
            return []
            
        except json.JSONDecodeError as e:
            logger.error(f"BochaAI 响应解析失败: {e}")
            return []
            
        except Exception as e:
            logger.error(f"BochaAI 搜索失败: {e}")
            return []
    
    def search_stock_news(
        self,
        stock_name: str,
        stock_code: Optional[str] = None,
        days: int = 30,
        count: int = 20,
    ) -> List[SearchResult]:
        """
        搜索股票相关新闻
        
        Args:
            stock_name: 股票名称（如"贵州茅台"）
            stock_code: 股票代码（可选，如"600519"）
            days: 搜索时间范围（天）
            count: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        # 构建搜索查询
        query_parts = [stock_name, "股票", "新闻"]
        if stock_code:
            # 提取纯数字代码
            pure_code = stock_code.upper()
            if pure_code.startswith("SH") or pure_code.startswith("SZ"):
                pure_code = pure_code[2:]
            query_parts.append(pure_code)
        
        query = " ".join(query_parts)
        
        # 确定时间范围
        if days <= 1:
            freshness = "day"
        elif days <= 7:
            freshness = "week"
        elif days <= 30:
            freshness = "month"
        else:
            freshness = "noLimit"
        
        # 财经网站列表（用于优先搜索）
        finance_sites = (
            "finance.sina.com.cn,"
            "stock.eastmoney.com,"
            "finance.qq.com,"
            "money.163.com,"
            "caijing.com.cn,"
            "yicai.com,"
            "nbd.com.cn,"
            "21jingji.com,"
            "eeo.com.cn,"
            "chinanews.com.cn"
        )
        
        return self.search(
            query=query,
            freshness=freshness,
            count=count,
            include_sites=finance_sites
        )


# 全局实例
bochaai_search = BochaAISearchTool()

