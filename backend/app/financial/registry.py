"""
Provider 注册中心

支持:
1. 动态注册/注销 Provider
2. 根据数据类型获取 Fetcher
3. 多 Provider 自动降级

来源参考:
- OpenBB: Provider Registry 机制
- 设计文档: research/codedeepresearch/OpenBB/FinnewsHunter_improvement_plan.md
"""
from typing import Dict, Optional, List
import logging

from .providers.base import BaseProvider, BaseFetcher

logger = logging.getLogger(__name__)


class ProviderNotFoundError(Exception):
    """Provider 未找到异常"""
    pass


class FetcherNotFoundError(Exception):
    """Fetcher 未找到异常"""
    pass


class ProviderRegistry:
    """
    Provider 注册中心

    功能:
    1. 注册/注销 Provider
    2. 根据数据类型获取 Fetcher
    3. 支持多 Provider 自动降级

    Example:
        >>> registry = ProviderRegistry()
        >>> registry.register(SinaProvider())
        >>> registry.register(TencentProvider())
        >>>
        >>> # 获取 Fetcher (按优先级自动选择)
        >>> fetcher = registry.get_fetcher("news")
        >>>
        >>> # 指定 Provider
        >>> fetcher = registry.get_fetcher("news", provider="tencent")
    """

    _instance: Optional["ProviderRegistry"] = None

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._providers: Dict[str, BaseProvider] = {}
            cls._instance._priority_order: List[str] = []
            cls._instance._initialized = False
        return cls._instance

    def register(self, provider: BaseProvider) -> None:
        """
        注册 Provider

        Args:
            provider: Provider 实例

        Note:
            - 如果 Provider 已存在，会被替换
            - 按 priority 自动排序
        """
        name = provider.info.name
        priority = provider.info.priority

        # 如果已存在，先移除
        if name in self._providers:
            self._priority_order.remove(name)

        self._providers[name] = provider

        # 按优先级插入（priority 越小越靠前）
        inserted = False
        for i, existing_name in enumerate(self._priority_order):
            existing_priority = self._providers[existing_name].info.priority
            if priority < existing_priority:
                self._priority_order.insert(i, name)
                inserted = True
                break

        if not inserted:
            self._priority_order.append(name)

        logger.info(
            f"Registered provider: {name} "
            f"(priority={priority}, types={list(provider.fetchers.keys())})"
        )

    def unregister(self, name: str) -> bool:
        """
        注销 Provider

        Args:
            name: Provider 名称

        Returns:
            是否成功注销
        """
        if name in self._providers:
            del self._providers[name]
            self._priority_order.remove(name)
            logger.info(f"Unregistered provider: {name}")
            return True
        return False

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        """
        获取指定 Provider

        Args:
            name: Provider 名称

        Returns:
            Provider 实例，如果不存在返回 None
        """
        return self._providers.get(name)

    def get_fetcher(
        self,
        data_type: str,
        provider: Optional[str] = None
    ) -> BaseFetcher:
        """
        获取 Fetcher，支持自动降级

        Args:
            data_type: 数据类型，如 'news', 'stock_price'
            provider: 可选的 Provider 名称，如果不指定则按优先级选择

        Returns:
            BaseFetcher 实例

        Raises:
            FetcherNotFoundError: 如果没有找到支持该数据类型的 Provider
            ProviderNotFoundError: 如果指定的 Provider 不存在

        Example:
            >>> # 自动选择最高优先级的 Provider
            >>> fetcher = registry.get_fetcher("news")
            >>>
            >>> # 指定 Provider
            >>> fetcher = registry.get_fetcher("news", provider="tencent")
        """
        # 如果指定了 Provider
        if provider:
            p = self._providers.get(provider)
            if not p:
                raise ProviderNotFoundError(f"Provider '{provider}' not found")

            fetcher = p.get_fetcher(data_type)
            if not fetcher:
                raise FetcherNotFoundError(
                    f"Provider '{provider}' does not support data_type='{data_type}'"
                )
            return fetcher

        # 否则按优先级选择
        for p_name in self._priority_order:
            p = self._providers[p_name]
            if p.supports(data_type):
                fetcher = p.get_fetcher(data_type)
                if fetcher:
                    logger.debug(f"Using {p_name} for {data_type}")
                    return fetcher

        # 没有找到支持的 Provider
        available = self.get_providers_for_type(data_type)
        raise FetcherNotFoundError(
            f"No provider found for data_type='{data_type}'. "
            f"Available providers for this type: {available}"
        )

    def list_providers(self) -> List[str]:
        """
        列出所有已注册的 Provider (按优先级排序)

        Returns:
            Provider 名称列表
        """
        return list(self._priority_order)

    def get_providers_for_type(self, data_type: str) -> List[str]:
        """
        获取支持指定数据类型的所有 Provider

        Args:
            data_type: 数据类型

        Returns:
            支持该类型的 Provider 名称列表 (按优先级排序)
        """
        return [
            name for name in self._priority_order
            if self._providers[name].supports(data_type)
        ]

    def get_all_data_types(self) -> List[str]:
        """
        获取所有支持的数据类型

        Returns:
            数据类型列表
        """
        types = set()
        for provider in self._providers.values():
            types.update(provider.fetchers.keys())
        return sorted(types)

    def clear(self) -> None:
        """清空所有注册的 Provider"""
        self._providers.clear()
        self._priority_order.clear()
        logger.info("Cleared all providers from registry")

    def __repr__(self) -> str:
        return f"<ProviderRegistry providers={self._priority_order}>"


# 全局单例
_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """
    获取全局 Registry 实例

    Returns:
        ProviderRegistry 单例
    """
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def reset_registry() -> ProviderRegistry:
    """
    重置全局 Registry (主要用于测试)

    Returns:
        新的 ProviderRegistry 实例
    """
    global _registry
    if _registry:
        _registry.clear()
    _registry = ProviderRegistry()
    _registry.clear()  # 确保单例也被清空
    return _registry
