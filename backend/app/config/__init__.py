"""
配置模块
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml
from pydantic import BaseModel, Field


# 配置目录
CONFIG_DIR = Path(__file__).parent


class AgentConfig(BaseModel):
    """智能体配置"""
    name: str
    role: str
    description: str


class FlowStep(BaseModel):
    """流程步骤配置"""
    name: str
    description: str
    parallel: bool = False
    agents: List[str] = Field(default_factory=list)
    type: Optional[str] = None
    max_rounds: Optional[int] = None


class FlowConfig(BaseModel):
    """流程配置"""
    type: str
    steps: List[FlowStep]


class ModeRules(BaseModel):
    """模式规则配置"""
    max_time: int = 300
    max_rounds: Optional[int] = None
    round_time_limit: Optional[int] = None
    manager_can_interrupt: bool = False
    require_news: bool = True
    require_financial: bool = True
    require_data_collection: bool = False
    early_decision: bool = False
    min_news_count: int = 0


class DebateRules(BaseModel):
    """辩论规则配置"""
    opening_statement: bool = True
    rebuttal_required: bool = True
    evidence_required: bool = True
    interrupt_cooldown: int = 30


class DebateModeConfig(BaseModel):
    """辩论模式配置"""
    name: str
    description: str
    icon: str = "📊"
    agents: List[AgentConfig]
    flow: FlowConfig
    rules: ModeRules
    debate_rules: Optional[DebateRules] = None


class LLMConfig(BaseModel):
    """LLM配置"""
    default_provider: str = "bailian"
    default_model: str = "qwen-plus"
    temperature: float = 0.7
    max_tokens: int = 4096


class DataSourceConfig(BaseModel):
    """数据源配置"""
    type: str
    priority: int = 1


class DataSourcesConfig(BaseModel):
    """数据源集合配置"""
    news: List[DataSourceConfig] = Field(default_factory=list)
    financial: List[DataSourceConfig] = Field(default_factory=list)


class OutputConfig(BaseModel):
    """输出配置"""
    format: str = "markdown"
    include_trajectory: bool = True
    include_timestamps: bool = True


class GlobalConfig(BaseModel):
    """全局配置"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    data_sources: DataSourcesConfig = Field(default_factory=DataSourcesConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


class DebateModesConfig(BaseModel):
    """辩论模式总配置"""
    default_mode: str = "parallel"
    modes: Dict[str, DebateModeConfig]
    global_config: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    
    class Config:
        populate_by_name = True


def load_debate_modes_config() -> DebateModesConfig:
    """加载辩论模式配置"""
    config_file = CONFIG_DIR / "debate_modes.yaml"
    
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_file}")
    
    with open(config_file, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)
    
    # 处理 global 关键字冲突
    if "global" in raw_config:
        raw_config["global_config"] = raw_config.pop("global")
    
    return DebateModesConfig(**raw_config)


def get_mode_config(mode_name: str) -> Optional[DebateModeConfig]:
    """获取指定模式的配置"""
    config = load_debate_modes_config()
    return config.modes.get(mode_name)


def get_available_modes() -> List[Dict[str, Any]]:
    """获取所有可用的模式列表"""
    config = load_debate_modes_config()
    modes = []
    for mode_id, mode_config in config.modes.items():
        modes.append({
            "id": mode_id,
            "name": mode_config.name,
            "description": mode_config.description,
            "icon": mode_config.icon,
            "is_default": mode_id == config.default_mode
        })
    return modes


def get_default_mode() -> str:
    """获取默认模式"""
    config = load_debate_modes_config()
    return config.default_mode


# 单例缓存
_cached_config: Optional[DebateModesConfig] = None


def get_cached_config() -> DebateModesConfig:
    """获取缓存的配置（避免重复读取文件）"""
    global _cached_config
    if _cached_config is None:
        _cached_config = load_debate_modes_config()
    return _cached_config


def reload_config() -> DebateModesConfig:
    """重新加载配置"""
    global _cached_config
    _cached_config = load_debate_modes_config()
    return _cached_config

