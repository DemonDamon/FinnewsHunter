# M12: Alpha Mining 量化因子挖掘模块

基于 AlphaGPT 技术的量化因子自动挖掘模块，使用符号回归 + 强化学习自动发现有预测能力的交易因子。

## 功能特性

- **因子自动发现**：使用 Transformer + RL 自动生成和优化因子表达式
- **DSL 表达式系统**：支持丰富的时序操作符（MA、STD、DELAY、DELTA 等）
- **情感特征融合**：可结合新闻情感分析提升因子效果
- **回测评估**：内置 Sortino/Sharpe/IC 等多种评估指标
- **AgenticX 集成**：提供 BaseTool 封装，供 Agent 调用

## 模块结构

```
alpha_mining/
├── __init__.py          # 模块入口
├── config.py            # 配置管理
├── utils.py             # 工具函数
├── dsl/                 # 因子表达式 DSL
│   ├── ops.py          # 操作符定义
│   └── vocab.py        # 词汇表管理
├── vm/                  # 因子执行器
│   └── factor_vm.py    # 栈式虚拟机
├── model/               # 生成模型
│   ├── alpha_generator.py  # Transformer 策略网络
│   └── trainer.py      # RL 训练器
├── features/            # 特征构建
│   ├── market.py       # 行情特征
│   └── sentiment.py    # 情感特征
├── backtest/            # 回测评估
│   └── evaluator.py    # 因子评估器
└── tools/               # AgenticX 工具
    └── alpha_mining_tool.py
```

## 快速开始

### 基础使用

```python
from app.alpha_mining import (
    AlphaGenerator,
    AlphaTrainer,
    FactorVM,
    FactorEvaluator,
    generate_mock_data
)

# 1. 准备数据
features, returns = generate_mock_data(
    num_samples=50,
    num_features=6,
    time_steps=252
)

# 2. 创建训练器
trainer = AlphaTrainer()

# 3. 训练挖掘因子
result = trainer.train(
    features=features,
    returns=returns,
    num_steps=100
)

print(f"最优因子: {result['best_formula_str']}")
print(f"得分: {result['best_score']:.4f}")
```

### 使用 QuantitativeAgent

```python
from app.agents import QuantitativeAgent

# 创建智能体
agent = QuantitativeAgent(
    llm_provider=llm,
    enable_alpha_mining=True
)

# 执行分析
result = await agent.analyze(
    stock_code="000001",
    stock_name="平安银行",
    market_data=market_data,
    sentiment_data=sentiment_data
)

# 获取发现的因子
for factor in result["factors_discovered"]:
    print(f"{factor['formula_str']}: Sortino={factor['sortino']:.2f}")
```

### REST API

```bash
# 启动因子挖掘任务
curl -X POST http://localhost:8000/api/v1/alpha-mining/mine \
  -H "Content-Type: application/json" \
  -d '{"num_steps": 100, "use_sentiment": true}'

# 评估因子表达式
curl -X POST http://localhost:8000/api/v1/alpha-mining/evaluate \
  -H "Content-Type: application/json" \
  -d '{"formula": "ADD(RET, MA5(VOL))"}'

# 获取已发现的因子
curl http://localhost:8000/api/v1/alpha-mining/factors?top_k=10
```

## 支持的操作符

### 算术操作符
| 操作符 | 参数数 | 描述 |
|--------|--------|------|
| ADD | 2 | 加法 |
| SUB | 2 | 减法 |
| MUL | 2 | 乘法 |
| DIV | 2 | 除法 |

### 一元操作符
| 操作符 | 参数数 | 描述 |
|--------|--------|------|
| NEG | 1 | 取负 |
| ABS | 1 | 绝对值 |
| SIGN | 1 | 符号函数 |

### 时序操作符
| 操作符 | 参数数 | 描述 |
|--------|--------|------|
| DELAY1/5 | 1 | 延迟 1/5 期 |
| DELTA1/5 | 1 | 差分 1/5 期 |
| MA5/10 | 1 | 5/10 日移动平均 |
| STD5/10 | 1 | 5/10 日滚动标准差 |

### 条件操作符
| 操作符 | 参数数 | 描述 |
|--------|--------|------|
| GATE | 3 | 条件选择 |
| MAX | 2 | 取最大值 |
| MIN | 2 | 取最小值 |

## 特征列表

| 特征 | 描述 | 数据来源 |
|------|------|----------|
| RET | 收益率 | 行情数据 |
| VOL | 波动率 | 行情数据 |
| VOLUME_CHG | 成交量变化 | 行情数据 |
| TURNOVER | 换手率 | 行情数据 |
| SENTIMENT | 情感分数 | 新闻分析 |
| NEWS_COUNT | 新闻数量 | 新闻分析 |

## 评估指标

- **Sortino Ratio**: 风险调整收益（只考虑下行风险）
- **Sharpe Ratio**: 风险调整收益
- **IC**: 信息系数（因子与收益的相关性）
- **Rank IC**: 排名信息系数
- **Max Drawdown**: 最大回撤
- **Turnover**: 换手率

## 配置选项

```python
from app.alpha_mining import AlphaMiningConfig

config = AlphaMiningConfig(
    # 模型参数
    d_model=64,           # Transformer 隐藏维度
    num_layers=2,         # Transformer 层数
    nhead=4,              # 注意力头数
    max_seq_len=12,       # 最大序列长度
    
    # 训练参数
    batch_size=1024,      # 批量大小
    lr=1e-3,              # 学习率
    num_steps=1000,       # 训练步数
    
    # 奖励参数
    invalid_formula_reward=-5.0,  # 无效公式惩罚
    constant_factor_reward=-2.0,  # 常量因子惩罚
    
    # 回测参数
    cost_rate=0.0015,     # 交易成本率
    signal_threshold=0.7, # 信号阈值
    
    # 特征配置
    enable_sentiment=True,  # 启用情感特征
)
```

## 参考

- [AlphaGPT](https://github.com/imbue-bit/AlphaGPT) - 原始实现