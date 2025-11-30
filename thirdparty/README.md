# 第三方开源金融智能体框架

本文件夹包含了截至2025年11月的主要开源金融智能体框架。以下是已成功克隆的仓库列表。

## 成功克隆的仓库 (20个)

### 一、多智能体协作框架

#### 1. TradingAgents系列
- **TradingAgents** - 多角色专业分工（分析师/研究员/交易员）
- **TradingAgents-CN** - 中文优化，支持A股/港股/国产大模型

#### 2. FinRL生态系统
- **FinRL** - 首个开源金融强化学习框架，三层架构
- **FinRL-Meta** - 市场环境库，300+真实交易环境
- **ElegantRL** - 轻量高效DRL库，FinRL的算法引擎

#### 3. 学术研究导向
- **FinRobot** - 四层架构，16个专业智能体分工
- **DISC-FinLLM** - 复旦DISC团队，投研团队模拟（NLPCC 2025获奖）

### 二、LLM+金融智能体框架

#### 1. 通用金融LLM智能体
- **FinGPT** - 金融大模型基座，支持多种下游任务

#### 2. 专业领域智能体
- **investor-agent** - MCP协议服务器，投资分析专用
- **agentic-trading** - Google ADK演示，A2A互操作性
- **FinGenius** - A股专用，博弈论决策机制

### 三、量化交易+智能体集成框架

#### 1. 成熟交易平台
- **vnpy** - 全功能量化框架，模块化设计
- **qlib** - 微软出品，AI量化投资平台
- **backtrader** - 经典回测框架，支持策略开发

#### 2. 专业工具集成
- **panda_quantflow** - 可视化工作流，节点式编排
- **FinceptTerminal** - CLI工具，技术/基本面/情绪分析

### 四、基础模型与数据框架

#### 1. 金融基础模型
- **Kronos** - K线基础模型，45个交易所预训练
- **FinCast-fts** - 时序预测基础模型，20B数据点

### 五、特色项目与工具

#### 1. 开发工具链
- **awesome-quant** - 量化资源精选列表
- **Lean** - QuantConnect算法交易引擎

## 克隆失败的仓库 (11个)

以下仓库在克隆时未找到或不存在：

1. **TradingAgents-Lite** - github.com/TauricResearch/TradingAgents-Lite
2. **HedgeAgents** - github.com/HedgeAgents/HedgeAgents
3. **FinMem** - github.com/FinMem/FinMem
4. **FinArena** - github.com/FinArena/FinArena
5. **FinHEAR** - github.com/FinHEAR/FinHEAR
6. **PulseReddit** - github.com/PulseReddit/PulseReddit
7. **mbt_gym** - github.com/mbt_gym/mbt_gym
8. **Agent-Trading-Arena** - github.com/Agent-Trading-Arena/Agent-Trading-Arena
9. **AI-Hedge-Fund** - github.com/AI-Hedge-Fund/AI-Hedge-Fund
10. **OpenBBTerminal** - github.com/OpenBB-finance/OpenBBTerminal (仓库过大，克隆超时)

## 说明

- 总计尝试克隆：31个仓库
- 成功克隆：20个仓库
- 失败原因：仓库不存在或已删除/重命名（10个），仓库过大超时（1个）
- 克隆时间：2025年11月30日

## 使用建议

建议根据具体需求选择合适的框架：
- **多智能体协作**：优先考虑 TradingAgents、FinRL、FinRobot
- **中文支持**：TradingAgents-CN、FinGenius
- **量化交易**：vnpy、qlib、backtrader
- **学术研究**：FinRL、DISC-FinLLM、Kronos
- **工具集成**：Lean、awesome-quant
