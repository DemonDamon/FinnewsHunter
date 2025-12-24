"""
并发多关键词检索策略
基于知识图谱的关键词，并发调用多个搜索API
"""
import logging
import asyncio
from typing import List, Dict, Any, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from ..tools.bochaai_search import bochaai_search
from .graph_models import SearchKeywordSet

logger = logging.getLogger(__name__)


class ParallelSearchStrategy:
    """
    并发检索策略
    基于知识图谱生成的关键词，并发搜索获取更全面的新闻
    """
    
    def __init__(self, max_workers: int = 5):
        """
        初始化并发检索策略
        
        Args:
            max_workers: 最大并发工作线程数
        """
        self.max_workers = max_workers
    
    def search_with_multiple_keywords(
        self,
        keyword_set: SearchKeywordSet,
        days: int = 30,
        max_results_per_query: int = 50
    ) -> List[Dict[str, Any]]:
        """
        使用多个关键词并发搜索
        
        Args:
            keyword_set: 关键词集合
            days: 搜索天数
            max_results_per_query: 每个查询的最大结果数
            
        Returns:
            去重后的新闻列表
        """
        # 生成多样化的搜索查询
        queries = keyword_set.generate_search_queries(max_queries=10)
        
        logger.info(f"🔍 开始并发检索: {keyword_set.stock_name}, 查询数={len(queries)}")
        logger.info(f"📋 查询列表: {queries}")
        
        all_results = []
        seen_urls: Set[str] = set()  # 用于去重
        
        # 并发执行搜索
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有搜索任务
            future_to_query = {}
            for query in queries:
                future = executor.submit(
                    self._search_single_query,
                    query,
                    days,
                    max_results_per_query
                )
                future_to_query[future] = query
            
            # 收集结果
            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    results = future.result()
                    
                    # 去重并添加
                    added_count = 0
                    for result in results:
                        if result.url not in seen_urls:
                            seen_urls.add(result.url)
                            all_results.append(result)
                            added_count += 1
                    
                    logger.info(f"✅ 查询「{query}」完成: 返回{len(results)}条, 去重后新增{added_count}条")
                    
                except Exception as e:
                    logger.error(f"❌ 查询「{query}」失败: {e}")
        
        logger.info(f"🎉 并发检索完成: 共获取 {len(all_results)} 条去重后的新闻")
        return all_results
    
    def _search_single_query(
        self,
        query: str,
        days: int,
        count: int
    ) -> List[Any]:
        """
        执行单个查询（在线程中运行）
        
        Args:
            query: 搜索查询
            days: 天数
            count: 结果数
            
        Returns:
            搜索结果列表
        """
        try:
            if not bochaai_search.is_available():
                return []
            
            # 调用 BochaAI 搜索
            results = bochaai_search.search(
                query=query,
                freshness="year",
                count=count,
                offset=0
            )
            
            return results
            
        except Exception as e:
            logger.error(f"搜索失败 {query}: {e}")
            return []
    
    async def search_async(
        self,
        keyword_set: SearchKeywordSet,
        days: int = 30,
        max_results_per_query: int = 50
    ) -> List[Dict[str, Any]]:
        """
        异步版本的并发搜索
        
        Args:
            keyword_set: 关键词集合
            days: 搜索天数
            max_results_per_query: 每个查询的最大结果数
            
        Returns:
            去重后的新闻列表
        """
        # 在线程池中运行同步搜索
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.search_with_multiple_keywords,
            keyword_set,
            days,
            max_results_per_query
        )


# 便捷函数
def create_parallel_search(max_workers: int = 5) -> ParallelSearchStrategy:
    """创建并发检索策略"""
    return ParallelSearchStrategy(max_workers=max_workers)

