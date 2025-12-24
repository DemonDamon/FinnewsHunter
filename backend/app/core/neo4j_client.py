"""
Neo4j 图数据库客户端
用于存储和查询公司知识图谱
"""
import logging
from typing import Optional, Dict, List, Any
from neo4j import GraphDatabase, Driver
from contextlib import contextmanager

from .config import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j 客户端封装"""
    
    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None
    ):
        """
        初始化 Neo4j 客户端
        
        Args:
            uri: Neo4j URI（如 bolt://localhost:7687）
            user: 用户名
            password: 密码
        """
        self.uri = uri or settings.NEO4J_URI or "bolt://localhost:7687"
        self.user = user or settings.NEO4J_USER or "neo4j"
        self.password = password or settings.NEO4J_PASSWORD or "finnews_neo4j_password"
        
        self._driver: Optional[Driver] = None
        self._connected = False
    
    def connect(self):
        """建立连接"""
        if self._connected:
            return
        
        try:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            # 测试连接
            self._driver.verify_connectivity()
            self._connected = True
            logger.info(f"✅ Neo4j 连接成功: {self.uri}")
        except Exception as e:
            logger.error(f"❌ Neo4j 连接失败: {e}")
            raise
    
    def close(self):
        """关闭连接"""
        if self._driver:
            self._driver.close()
            self._connected = False
            logger.info("Neo4j 连接已关闭")
    
    @contextmanager
    def session(self):
        """获取会话（上下文管理器）"""
        if not self._connected:
            self.connect()
        
        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()
    
    def execute_query(
        self,
        query: str,
        parameters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        执行 Cypher 查询
        
        Args:
            query: Cypher 查询语句
            parameters: 查询参数
            
        Returns:
            查询结果列表
        """
        with self.session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]
    
    def execute_write(
        self,
        query: str,
        parameters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        执行写入操作
        
        Args:
            query: Cypher 写入语句
            parameters: 参数
            
        Returns:
            写入结果
        """
        with self.session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            if not self._connected:
                self.connect()
            
            with self.session() as session:
                result = session.run("RETURN 1 as health")
                return result.single()["health"] == 1
        except Exception as e:
            logger.error(f"Neo4j 健康检查失败: {e}")
            return False


# 全局单例
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    """获取 Neo4j 客户端单例"""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
        _neo4j_client.connect()
    return _neo4j_client


def close_neo4j_client():
    """关闭 Neo4j 客户端"""
    global _neo4j_client
    if _neo4j_client:
        _neo4j_client.close()
        _neo4j_client = None

