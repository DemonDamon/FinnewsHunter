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
        offset: int = 0,
        include_sites: Optional[str] = None,
        exclude_sites: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        执行 Web 搜索
        
        Args:
            query: 搜索查询字符串
            freshness: 时间范围（noLimit, day, week, month）
            count: 返回结果数量（1-50，单次最大50条）
            offset: 结果偏移量（用于分页）
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
            
            # 添加 offset 参数进行分页
            if offset > 0:
                request_data["offset"] = offset
            
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
            
            logger.info(f"BochaAI 搜索完成: query='{query}', offset={offset}, 结果数={len(results)}")
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
        count: int = 100,
        max_age_days: int = 365,
    ) -> List[SearchResult]:
        """
        搜索股票相关新闻
        
        Args:
            stock_name: 股票名称（如"贵州茅台"）
            stock_code: 股票代码（可选，如"600519"）
            days: 搜索时间范围（天），用于API freshness参数
            count: 返回结果数量（支持超过50条，会自动分页请求）
            max_age_days: 最大新闻年龄（天），默认365天（1年），超过此时间的新闻将被过滤
            
        Returns:
            搜索结果列表（按时间从新到旧排序，只返回最近max_age_days天内的新闻）
        """
        # 构建搜索查询 - 简洁明确，添加"最新"关键词优先获取新内容
        query = f"{stock_name} 最新"
        
        # BochaAI API 支持的 freshness 参数值：
        # - noLimit: 不限制
        # - oneDay: 一天内
        # - oneWeek: 一周内  
        # - oneMonth: 一月内
        # 注意：不支持 "year"、"day"、"week" 等其他值！
        
        # 根据请求天数确定 freshness 参数
        if days <= 1:
            freshness = "oneDay"
        elif days <= 7:
            freshness = "oneWeek"
        elif days <= 30:
            freshness = "oneMonth"
        else:
            freshness = "noLimit"  # 超过30天用 noLimit，本地再过滤
        
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
        
        # 计算截止时间（半年前）
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        all_results = []
        offset = 0
        batch_size = 50  # API单次最大返回数
        max_requests = 5  # 最多请求5次，防止无限循环
        request_count = 0
        
        logger.info(f"BochaAI 开始搜索股票新闻: {stock_name}, 目标数量={count}, 截止日期={cutoff_date.strftime('%Y-%m-%d')}")
        
        while len(all_results) < count and request_count < max_requests:
            batch_results = self.search(
                query=query,
                freshness=freshness,
                count=batch_size,
                offset=offset,
                include_sites=finance_sites
            )
            
            if not batch_results:
                logger.info(f"BochaAI 第{request_count+1}次请求未返回结果，停止分页")
                break
            
            # 时间过滤：保留有日期且在范围内的新闻，以及无日期但可能相关的新闻
            for result in batch_results:
                # 如果有发布日期，检查是否在时间范围内
                if result.date_published:
                    try:
                        # 尝试解析发布时间
                        pub_date = datetime.fromisoformat(
                            result.date_published.replace('Z', '+00:00')
                        )
                        # 转换为无时区的时间进行比较
                        if pub_date.tzinfo:
                            pub_date = pub_date.replace(tzinfo=None)
                        
                        # 检查是否在指定时间范围内
                        if pub_date < cutoff_date:
                            logger.debug(f"过滤超过{max_age_days}天的新闻: {result.title[:30]}... ({result.date_published})")
                            continue
                            
                    except (ValueError, AttributeError) as e:
                        # 日期解析失败，但仍然保留（可能是新闻）
                        logger.debug(f"无法解析日期，但仍保留: {result.title[:30]}...")
                else:
                    # 无日期的新闻也保留（可能是相关新闻）
                    logger.debug(f"无日期新闻，保留: {result.title[:30]}...")
                
                # 添加到结果中
                all_results.append(result)
                
                if len(all_results) >= count:
                    break
            
            offset += batch_size
            request_count += 1
            logger.info(f"BochaAI 第{request_count}次请求完成，当前累计 {len(all_results)} 条有效结果")
        
        # 按发布时间排序（从新到旧）
        def parse_date(r):
            if r.date_published:
                try:
                    dt = datetime.fromisoformat(r.date_published.replace('Z', '+00:00'))
                    if dt.tzinfo:
                        dt = dt.replace(tzinfo=None)
                    return dt
                except (ValueError, AttributeError):
                    pass
            return datetime.min  # 无法解析的日期排在最后
        
        all_results.sort(key=parse_date, reverse=True)
        
        logger.info(f"BochaAI 搜索股票新闻完成: {stock_name}, 返回 {len(all_results)} 条结果 (共请求{request_count}次, 仅保留最近{max_age_days}天即{max_age_days//30}个月内)")
        
        return all_results[:count]  # 确保不超过请求数量


# 全局实例
bochaai_search = BochaAISearchTool()

