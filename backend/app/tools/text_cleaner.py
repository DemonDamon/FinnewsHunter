"""
文本清洗工具
重构自 legacy_v1/src/Killua/
"""
import re
import logging
from typing import List, Set
import jieba

from agenticx import BaseTool
from agenticx.core import ToolMetadata, ToolCategory

logger = logging.getLogger(__name__)


class TextCleanerTool(BaseTool):
    """
    文本清洗工具
    提供去停用词、分词、文本标准化等功能
    """
    
    # 中文停用词列表（简化版）
    STOP_WORDS = {
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
        '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
        '看', '好', '自己', '这', '那', '里', '就是', '什么', '可以', '为', '以',
        '及', '等', '将', '并', '个', '与', '对', '如', '所', '于', '被', '由',
        '从', '而', '把', '让', '向', '却', '但', '或', '及', '但是', '然而',
        '因为', '所以', '如果', '虽然', '尽管', '无论', '不管', '只要', '除非',
        '、', '，', '。', '；', '：', '？', '！', '"', '"', ''', ''', '（', '）',
        '【', '】', '《', '》', '—', '…', '·', '~', '#', '@', '&',
    }
    
    def __init__(self):
        metadata = ToolMetadata(
            name="text_cleaner",
            description="Clean and preprocess Chinese financial text",
            category=ToolCategory.UTILITY,
            version="1.0.0"
        )
        super().__init__(metadata=metadata)
        # 初始化jieba
        jieba.setLogLevel(logging.WARNING)
        
        # 加载金融领域自定义词典（可选）
        self._load_custom_dict()
    
    def _load_custom_dict(self):
        """加载自定义词典"""
        # 金融领域常用词
        financial_words = [
            '股票', '证券', '基金', '债券', '期货', '期权', '外汇',
            '上证指数', '深证成指', '创业板', '科创板',
            '涨停', '跌停', '停牌', '复牌', '退市', '上市',
            '市盈率', '市净率', '市值', '流通股', '限售股',
            '分红', '配股', '增发', '回购', '重组', '并购',
            '利好', '利空', '看多', '看空', '做多', '做空',
            '成交量', '换手率', '振幅', '量比',
        ]
        
        for word in financial_words:
            jieba.add_word(word)
    
    def clean_text(self, text: str) -> str:
        """
        基础文本清洗
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        if not text:
            return ""
        
        # 移除URL
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # 移除邮箱
        text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text)
        
        # 移除特殊字符（保留中文、英文、数字）
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\.\,\!\?\:\;\-\%\(\)]', '', text)
        
        # 统一空格
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def tokenize(self, text: str, remove_stopwords: bool = True) -> List[str]:
        """
        中文分词
        
        Args:
            text: 文本
            remove_stopwords: 是否去除停用词
            
        Returns:
            词语列表
        """
        # 分词
        words = jieba.cut(text)
        
        # 过滤
        result = []
        for word in words:
            word = word.strip()
            if not word:
                continue
            
            # 去除停用词
            if remove_stopwords and word in self.STOP_WORDS:
                continue
            
            # 去除单字符（除了一些特殊字如"涨"、"跌"）
            if len(word) == 1 and not re.match(r'[\u4e00-\u9fa5]', word):
                continue
            
            result.append(word)
        
        return result
    
    def extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """
        提取关键词
        
        Args:
            text: 文本
            top_k: 返回的关键词数量
            
        Returns:
            关键词列表
        """
        import jieba.analyse
        
        keywords = jieba.analyse.extract_tags(
            text,
            topK=top_k,
            withWeight=False
        )
        return keywords
    
    def normalize_stock_code(self, code: str) -> str:
        """
        标准化股票代码
        
        Args:
            code: 原始代码（如 sh600519, 600519, SH600519）
            
        Returns:
            标准化代码（如 600519）
        """
        code = code.upper().strip()
        # 移除市场前缀
        code = re.sub(r'^(SH|SZ|HK)', '', code)
        return code
    
    def _setup_parameters(self):
        """设置工具参数（AgenticX 要求）"""
        # TextCleanerTool 的参数通过 execute 方法的 kwargs 传递
        pass
    
    def execute(self, **kwargs) -> dict:
        """
        同步执行方法（AgenticX Tool 协议要求）
        
        Args:
            **kwargs: 参数字典
                - text: 输入文本（必需）
                - operation: 操作类型（clean, tokenize, keywords），默认 "clean"
                - remove_stopwords: 是否去除停用词（仅用于 tokenize），默认 True
                - top_k: 关键词数量（仅用于 keywords），默认 10
                
        Returns:
            执行结果
        """
        text = kwargs.get("text", "")
        if not text:
            return {"success": False, "error": "Missing required parameter: text"}
        
        operation = kwargs.get("operation", "clean")
        
        if operation == "clean":
            result = self.clean_text(text)
            return {"success": True, "result": result}
        
        elif operation == "tokenize":
            remove_stopwords = kwargs.get("remove_stopwords", True)
            result = self.tokenize(text, remove_stopwords)
            return {"success": True, "result": result, "count": len(result)}
        
        elif operation == "keywords":
            top_k = kwargs.get("top_k", 10)
            result = self.extract_keywords(text, top_k)
            return {"success": True, "result": result}
        
        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}
    
    async def aexecute(self, **kwargs) -> dict:
        """
        异步执行方法（AgenticX Tool 协议要求）
        当前实现为同步执行的包装
        
        Args:
            **kwargs: 参数字典
                
        Returns:
            执行结果
        """
        return self.execute(**kwargs)


# 便捷创建函数
def create_text_cleaner() -> TextCleanerTool:
    """创建文本清洗工具实例"""
    return TextCleanerTool()

