"""
新浪财经 Provider

提供:
- 新闻数据 (news): SinaNewsFetcher

从 tools/sina_crawler.py 迁移而来，保留核心逻辑，
适配 TET Pipeline 架构。
"""
from .provider import SinaProvider

__all__ = ["SinaProvider"]
