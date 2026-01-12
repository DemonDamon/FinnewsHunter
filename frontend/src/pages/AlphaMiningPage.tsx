/**
 * Alpha Mining 因子挖掘页面（增强版）
 * 
 * 技术亮点展示：
 * - 符号回归 + RL: Transformer 策略网络 + REINFORCE 算法
 * - DSL 系统: 21 个时序/算术/条件操作符
 * - 情感融合: 支持新闻情感特征增强因子效果
 * - 完整评估: Sortino/Sharpe/IC/Rank IC 等指标
 * - AgenticX 集成: BaseTool 封装，支持 Agent 调用
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { alphaMiningApi } from '../lib/api-client';
import type { AlphaMiningFactor, AlphaMiningMetrics } from '../lib/api-client';
import {
  OperatorGrid,
  TrainingMonitor,
  MetricsDashboard,
  SentimentCompare,
  AgentDemo,
} from '../components/alpha-mining';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import {
  Zap, Code, BarChart2, Heart, Bot,
  RefreshCw, ChevronRight, Sparkles, Brain
} from 'lucide-react';
import { useLanguageStore } from '@/store/useLanguageStore';

// ============================================================================
// 国际化文案
// ============================================================================

const i18n = {
  zh: {
    title: 'Alpha因子挖掘',
    subtitle: '基于 AlphaGPT 的量化因子自动挖掘系统',
    tabs: {
      overview: '概览',
      training: '训练',
      evaluate: '评估',
      sentiment: '情感融合',
      agent: 'Agent',
    },
    techBadges: {
      rl: '符号回归 + RL',
      dsl: '21 个 DSL 操作符',
      sentiment: '情感融合',
      metrics: '完整评估体系',
      agent: 'AgenticX 集成',
    },
    dsl: {
      title: 'DSL 操作符系统',
      desc: '21 个可组合操作符，支持算术/时序/条件运算',
    },
    factors: {
      title: '已发现的因子',
      desc: '按 Sortino Ratio 排序的最优因子',
      empty: '暂无已发现的因子',
      emptyHint: '去"训练"标签页启动因子挖掘',
      loading: '加载中...',
    },
    arch: {
      title: '系统架构',
      features: '特征数据',
      featuresDesc: '行情 + 情感',
      generator: 'AlphaGenerator',
      generatorDesc: 'Transformer',
      vm: 'FactorVM',
      vmDesc: 'StackVM 执行',
      evaluator: 'Evaluator',
      evaluatorDesc: '回测评估',
      rl: 'REINFORCE',
      rlDesc: '策略梯度',
    },
    evaluate: {
      expression: '因子表达式',
      placeholder: '点击下方操作符构建表达式，如: ADD(RET, MA5(VOL))',
      button: '评估因子',
      evaluating: '评估中...',
      operators: '操作符',
    },
  },
  en: {
    title: 'Alpha Mining',
    subtitle: '',
    tabs: {
      overview: 'Overview',
      training: 'Training',
      evaluate: 'Evaluate',
      sentiment: 'Sentiment',
      agent: 'Agent',
    },
    techBadges: {
      rl: 'Symbolic Regression + RL',
      dsl: '21 DSL Operators',
      sentiment: 'Sentiment Fusion',
      metrics: 'Full Evaluation',
      agent: 'AgenticX Integration',
    },
    dsl: {
      title: 'DSL Operator System',
      desc: '21 composable operators for arithmetic/timeseries/conditional operations',
    },
    factors: {
      title: 'Discovered Factors',
      desc: 'Top factors ranked by Sortino Ratio',
      empty: 'No factors discovered yet',
      emptyHint: 'Go to "Training" tab to start factor mining',
      loading: 'Loading...',
    },
    arch: {
      title: 'System Architecture',
      features: 'Features',
      featuresDesc: 'Price + Sentiment',
      generator: 'AlphaGenerator',
      generatorDesc: 'Transformer',
      vm: 'FactorVM',
      vmDesc: 'StackVM Executor',
      evaluator: 'Evaluator',
      evaluatorDesc: 'Backtesting',
      rl: 'REINFORCE',
      rlDesc: 'Policy Gradient',
    },
    evaluate: {
      expression: 'Factor Expression',
      placeholder: 'Click operators below to build expression, e.g.: ADD(RET, MA5(VOL))',
      button: 'Evaluate',
      evaluating: 'Evaluating...',
      operators: 'Operators',
    },
  },
};

// ============================================================================
// 主页面组件
// ============================================================================

const AlphaMiningPage: React.FC = () => {
  const { lang } = useLanguageStore();
  const [activeTab, setActiveTab] = useState('overview');
  const [factors, setFactors] = useState<AlphaMiningFactor[]>([]);
  const [isLoadingFactors, setIsLoadingFactors] = useState(true);
  const [evaluateFormula, setEvaluateFormula] = useState('');
  const [evaluateResult, setEvaluateResult] = useState<AlphaMiningMetrics | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);

  const t = i18n[lang];

  // 加载已发现的因子
  const loadFactors = useCallback(async () => {
    setIsLoadingFactors(true);
    try {
      const response = await alphaMiningApi.getFactors(20);
      setFactors(response.factors || []);
    } catch (error) {
      console.error('Failed to load factors:', error);
    } finally {
      setIsLoadingFactors(false);
    }
  }, []);

  useEffect(() => {
    loadFactors();
  }, [loadFactors]);

  // 评估因子
  const handleEvaluate = useCallback(async () => {
    if (!evaluateFormula.trim()) return;
    
    setIsEvaluating(true);
    try {
      const response = await alphaMiningApi.evaluate({ formula: evaluateFormula });
      if (response.success && response.metrics) {
        setEvaluateResult(response.metrics);
      }
    } catch (error) {
      console.error('Evaluate error:', error);
    } finally {
      setIsEvaluating(false);
    }
  }, [evaluateFormula]);

  // 插入操作符到表达式
  const handleOperatorClick = (op: string) => {
    setEvaluateFormula(prev => prev ? `${prev} ${op}` : op);
  };

  // 插入特征到表达式
  const handleFeatureClick = (feature: string) => {
    setEvaluateFormula(prev => prev ? `${prev} ${feature}` : feature);
  };

  // 训练完成回调
  const handleTrainingComplete = useCallback((result: { best_score: number; best_formula: string }) => {
    loadFactors(); // 刷新因子列表
    if (result.best_formula) {
      setEvaluateFormula(result.best_formula);
    }
  }, [loadFactors]);

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      {/* 页面标题 */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-br from-amber-400 to-orange-500 rounded-lg">
            <Brain className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">{t.title}</h1>
            {t.subtitle && <p className="text-gray-600 text-sm">{t.subtitle}</p>}
          </div>
        </div>
        
        {/* 技术亮点标签 */}
        <div className="flex flex-wrap gap-2 mt-4">
          <TechBadge icon={<Zap className="w-3 h-3" />} label={t.techBadges.rl} />
          <TechBadge icon={<Code className="w-3 h-3" />} label={t.techBadges.dsl} />
          <TechBadge icon={<Heart className="w-3 h-3" />} label={t.techBadges.sentiment} />
          <TechBadge icon={<BarChart2 className="w-3 h-3" />} label={t.techBadges.metrics} />
          <TechBadge icon={<Bot className="w-3 h-3" />} label={t.techBadges.agent} />
        </div>
      </div>

      {/* 主内容区 - Tab 切换 */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid grid-cols-5 w-full max-w-2xl">
          <TabsTrigger value="overview" className="gap-1">
            <Sparkles className="w-4 h-4" />
            {t.tabs.overview}
          </TabsTrigger>
          <TabsTrigger value="training" className="gap-1">
            <Zap className="w-4 h-4" />
            {t.tabs.training}
          </TabsTrigger>
          <TabsTrigger value="evaluate" className="gap-1">
            <BarChart2 className="w-4 h-4" />
            {t.tabs.evaluate}
          </TabsTrigger>
          <TabsTrigger value="sentiment" className="gap-1">
            <Heart className="w-4 h-4" />
            {t.tabs.sentiment}
          </TabsTrigger>
          <TabsTrigger value="agent" className="gap-1">
            <Bot className="w-4 h-4" />
            {t.tabs.agent}
          </TabsTrigger>
        </TabsList>

        {/* 概览 Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* DSL 操作符展示 */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Code className="w-5 h-5 text-blue-500" />
                  {t.dsl.title}
                </CardTitle>
                <CardDescription>{t.dsl.desc}</CardDescription>
              </CardHeader>
              <CardContent>
                <OperatorGrid
                  onOperatorClick={handleOperatorClick}
                  onFeatureClick={handleFeatureClick}
                  compact
                />
              </CardContent>
            </Card>

            {/* 已发现的因子 */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Sparkles className="w-5 h-5 text-amber-500" />
                      {t.factors.title}
                    </CardTitle>
                    <CardDescription>{t.factors.desc}</CardDescription>
                  </div>
                  <Button variant="outline" size="sm" onClick={loadFactors}>
                    <RefreshCw className={`w-4 h-4 ${isLoadingFactors ? 'animate-spin' : ''}`} />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {isLoadingFactors ? (
                  <div className="text-center py-8 text-gray-500">
                    {t.factors.loading}
                  </div>
                ) : factors.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <Sparkles className="w-10 h-10 mx-auto opacity-50 mb-2" />
                    <p>{t.factors.empty}</p>
                    <p className="text-sm mt-1">{t.factors.emptyHint}</p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {factors.slice(0, 10).map((factor, idx) => (
                      <FactorCard
                        key={idx}
                        factor={factor}
                        rank={idx + 1}
                        onSelect={() => setEvaluateFormula(factor.formula_str)}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* 系统架构说明 */}
          <Card className="bg-gradient-to-r from-indigo-50 to-purple-50">
            <CardContent className="py-6">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Brain className="w-5 h-5 text-indigo-500" />
                {t.arch.title}
              </h3>
              <div className="flex items-center justify-center gap-2 flex-wrap">
                <ArchNode label={t.arch.features} sub={t.arch.featuresDesc} />
                <ChevronRight className="w-4 h-4 text-gray-400" />
                <ArchNode label={t.arch.generator} sub={t.arch.generatorDesc} highlight />
                <ChevronRight className="w-4 h-4 text-gray-400" />
                <ArchNode label={t.arch.vm} sub={t.arch.vmDesc} />
                <ChevronRight className="w-4 h-4 text-gray-400" />
                <ArchNode label={t.arch.evaluator} sub={t.arch.evaluatorDesc} />
                <ChevronRight className="w-4 h-4 text-gray-400" />
                <ArchNode label={t.arch.rl} sub={t.arch.rlDesc} highlight />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* 训练 Tab */}
        <TabsContent value="training">
          <TrainingMonitor onTrainingComplete={handleTrainingComplete} />
        </TabsContent>

        {/* 评估 Tab */}
        <TabsContent value="evaluate" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* 左侧：操作符和输入 */}
            <div className="space-y-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{t.evaluate.expression}</CardTitle>
                </CardHeader>
                <CardContent>
                  <textarea
                    value={evaluateFormula}
                    onChange={(e) => setEvaluateFormula(e.target.value)}
                    placeholder={t.evaluate.placeholder}
                    className="w-full px-3 py-2 border rounded-md font-mono text-sm h-24"
                  />
                  <Button
                    onClick={handleEvaluate}
                    disabled={isEvaluating || !evaluateFormula.trim()}
                    className="w-full mt-2"
                  >
                    {isEvaluating ? t.evaluate.evaluating : t.evaluate.button}
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{t.evaluate.operators}</CardTitle>
                </CardHeader>
                <CardContent>
                  <OperatorGrid
                    onOperatorClick={handleOperatorClick}
                    onFeatureClick={handleFeatureClick}
                    compact
                  />
                </CardContent>
              </Card>
            </div>

            {/* 右侧：评估结果 */}
            <div className="lg:col-span-2">
              <MetricsDashboard
                metrics={evaluateResult}
                formula={evaluateFormula}
                loading={isEvaluating}
              />
            </div>
          </div>
        </TabsContent>

        {/* 情感融合 Tab */}
        <TabsContent value="sentiment">
          <SentimentCompare />
        </TabsContent>

        {/* Agent Tab */}
        <TabsContent value="agent">
          <AgentDemo />
        </TabsContent>
      </Tabs>
    </div>
  );
};

// ============================================================================
// 子组件
// ============================================================================

// 技术亮点徽章
const TechBadge: React.FC<{ icon: React.ReactNode; label: string }> = ({ icon, label }) => (
  <Badge variant="outline" className="gap-1 px-2 py-1">
    {icon}
    {label}
  </Badge>
);

// 因子卡片
interface FactorCardProps {
  factor: AlphaMiningFactor;
  rank: number;
  onSelect: () => void;
}

const FactorCard: React.FC<FactorCardProps> = ({ factor, rank, onSelect }) => {
  const getSortinoColor = (sortino: number) => {
    if (sortino > 1) return 'text-green-600 bg-green-50';
    if (sortino > 0) return 'text-amber-600 bg-amber-50';
    return 'text-red-600 bg-red-50';
  };

  return (
    <div
      className="p-3 border rounded-lg hover:shadow-sm transition-shadow cursor-pointer"
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 font-medium">#{rank}</span>
          <code className="text-sm font-mono truncate max-w-[200px]" title={factor.formula_str}>
            {factor.formula_str}
          </code>
        </div>
        <Badge className={`text-xs ${getSortinoColor(factor.sortino)}`}>
          {factor.sortino.toFixed(3)}
        </Badge>
      </div>
      {factor.discovered_at && (
        <div className="text-xs text-gray-400 mt-1">
          {new Date(factor.discovered_at).toLocaleString()}
        </div>
      )}
    </div>
  );
};

// 架构节点
const ArchNode: React.FC<{ label: string; sub: string; highlight?: boolean }> = ({
  label,
  sub,
  highlight,
}) => (
  <div className={`
    px-4 py-2 rounded-lg text-center
    ${highlight ? 'bg-indigo-100 border-2 border-indigo-300' : 'bg-white border border-gray-200'}
  `}>
    <div className={`text-sm font-medium ${highlight ? 'text-indigo-700' : ''}`}>{label}</div>
    <div className="text-xs text-gray-500">{sub}</div>
  </div>
);

export default AlphaMiningPage;
