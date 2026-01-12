/**
 * 完整评估指标仪表盘
 * 
 * 展示因子评估的所有指标：
 * - 雷达图：多维度指标可视化
 * - 收益曲线：策略收益 vs 基准
 * - 风险指标卡片
 */

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Badge } from '../ui/badge';
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Area, AreaChart, BarChart, Bar
} from 'recharts';
import {
  TrendingUp, TrendingDown, Activity, AlertTriangle,
  Target, BarChart2, PieChart, Percent
} from 'lucide-react';
import { useGlobalI18n } from '@/store/useLanguageStore';

export interface FactorMetrics {
  sortino_ratio: number;
  sharpe_ratio: number;
  ic: number;
  rank_ic: number;
  max_drawdown: number;
  turnover: number;
  total_return: number;
  win_rate: number;
  avg_return?: number;
}

interface MetricsDashboardProps {
  metrics: FactorMetrics | null;
  formula?: string;
  loading?: boolean;
  returnsCurve?: { date: string; strategy: number; benchmark: number }[];
}

const MetricsDashboard: React.FC<MetricsDashboardProps> = ({
  metrics,
  formula,
  loading = false,
  returnsCurve,
}) => {
  const t = useGlobalI18n();
  
  if (loading) {
    return (
      <Card className="w-full animate-pulse">
        <CardHeader>
          <div className="h-6 bg-gray-200 rounded w-1/3" />
        </CardHeader>
        <CardContent>
          <div className="h-64 bg-gray-100 rounded" />
        </CardContent>
      </Card>
    );
  }

  if (!metrics) {
    return (
      <Card className="w-full">
        <CardContent className="py-12 text-center text-gray-500">
          <BarChart2 className="w-12 h-12 mx-auto opacity-50 mb-3" />
          <p>{t.alphaMining.metrics.noData}</p>
          <p className="text-sm mt-1">{t.alphaMining.metrics.hint}</p>
        </CardContent>
      </Card>
    );
  }

  // 雷达图数据（归一化到 0-100）
  const radarData = [
    { 
      metric: 'Sortino', 
      value: normalizeMetric(metrics.sortino_ratio, -2, 5), 
      fullMark: 100 
    },
    { 
      metric: 'Sharpe', 
      value: normalizeMetric(metrics.sharpe_ratio, -2, 3), 
      fullMark: 100 
    },
    { 
      metric: 'IC', 
      value: normalizeMetric(metrics.ic, -0.3, 0.3) , 
      fullMark: 100 
    },
    { 
      metric: 'Rank IC', 
      value: normalizeMetric(metrics.rank_ic, -0.3, 0.3), 
      fullMark: 100 
    },
    { 
      metric: 'Win Rate', 
      value: metrics.win_rate * 100, 
      fullMark: 100 
    },
    { 
      metric: t.alphaMining.metrics.lowTurnover, 
      value: 100 - metrics.turnover * 100, 
      fullMark: 100 
    },
  ];

  // 评级逻辑
  const rating = getFactorRating(metrics, t);

  return (
    <div className="space-y-4">
      {/* 因子表达式 & 评级 */}
      {formula && (
        <Card className="bg-gradient-to-r from-blue-50 to-indigo-50">
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-gray-500 mb-1">{t.alphaMining.metrics.currentFactor}</div>
                <code className="text-sm font-mono font-medium text-gray-800">
                  {formula}
                </code>
              </div>
              <Badge className={rating.className}>
                {rating.icon}
                <span className="ml-1">{rating.label}</span>
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 主要指标卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Sortino Ratio"
          value={metrics.sortino_ratio.toFixed(4)}
          description={t.alphaMining.metrics.maxDrawdown}
          icon={<Target className="w-4 h-4" />}
          trend={metrics.sortino_ratio > 0 ? 'up' : 'down'}
          good={metrics.sortino_ratio > 1}
        />
        <MetricCard
          label="Sharpe Ratio"
          value={metrics.sharpe_ratio.toFixed(4)}
          description={t.alphaMining.metrics.maxDrawdown}
          icon={<TrendingUp className="w-4 h-4" />}
          trend={metrics.sharpe_ratio > 0 ? 'up' : 'down'}
          good={metrics.sharpe_ratio > 0.5}
        />
        <MetricCard
          label="IC"
          value={metrics.ic.toFixed(4)}
          description={t.alphaMining.metrics.maxDrawdown}
          icon={<Activity className="w-4 h-4" />}
          trend={metrics.ic > 0 ? 'up' : 'down'}
          good={Math.abs(metrics.ic) > 0.03}
        />
        <MetricCard
          label="Rank IC"
          value={metrics.rank_ic.toFixed(4)}
          description={t.alphaMining.metrics.maxDrawdown}
          icon={<BarChart2 className="w-4 h-4" />}
          trend={metrics.rank_ic > 0 ? 'up' : 'down'}
          good={Math.abs(metrics.rank_ic) > 0.03}
        />
      </div>

      {/* 雷达图 & 风险指标 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 雷达图 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <PieChart className="w-4 h-4 text-indigo-500" />
              {t.alphaMining.metrics.multiDim}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#e5e7eb" />
                  <PolarAngleAxis 
                    dataKey="metric" 
                    tick={{ fontSize: 11, fill: '#6b7280' }}
                  />
                  <PolarRadiusAxis 
                    angle={30} 
                    domain={[0, 100]} 
                    tick={{ fontSize: 10 }}
                  />
                  <Radar
                    name={t.alphaMining.metrics.currentFactor}
                    dataKey="value"
                    stroke="#6366f1"
                    fill="#6366f1"
                    fillOpacity={0.3}
                    strokeWidth={2}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(255, 255, 255, 0.95)',
                      borderRadius: '8px',
                      border: '1px solid #e5e7eb',
                      fontSize: 12,
                    }}
                    formatter={(value: number) => [`${value.toFixed(1)}`, t.alphaMining.metrics.currentFactor]}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* 风险指标 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              {t.alphaMining.metrics.riskMetrics}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* 最大回撤 */}
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600">{t.alphaMining.metrics.maxDrawdown}</span>
                <span className={metrics.max_drawdown > 0.2 ? 'text-red-600 font-medium' : 'text-gray-800'}>
                  {(metrics.max_drawdown * 100).toFixed(2)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${
                    metrics.max_drawdown > 0.3 ? 'bg-red-500' :
                    metrics.max_drawdown > 0.2 ? 'bg-amber-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${Math.min(metrics.max_drawdown * 100, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>0%</span>
                <span>{t.alphaMining.metrics.safe}</span>
                <span>{t.alphaMining.metrics.danger}</span>
                <span>100%</span>
              </div>
            </div>

            {/* 换手率 */}
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600">{t.alphaMining.metrics.dailyTurnover}</span>
                <span className={metrics.turnover > 0.5 ? 'text-amber-600 font-medium' : 'text-gray-800'}>
                  {(metrics.turnover * 100).toFixed(2)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${
                    metrics.turnover > 0.5 ? 'bg-amber-500' : 'bg-blue-500'
                  }`}
                  style={{ width: `${Math.min(metrics.turnover * 100, 100)}%` }}
                />
              </div>
            </div>

            {/* 胜率 */}
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600">{t.alphaMining.metrics.winRate}</span>
                <span className={metrics.win_rate > 0.5 ? 'text-green-600 font-medium' : 'text-gray-800'}>
                  {(metrics.win_rate * 100).toFixed(2)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${
                    metrics.win_rate > 0.55 ? 'bg-green-500' :
                    metrics.win_rate > 0.5 ? 'bg-blue-500' : 'bg-gray-400'
                  }`}
                  style={{ width: `${metrics.win_rate * 100}%` }}
                />
              </div>
            </div>

            {/* 总收益 */}
            <div className="pt-2 border-t">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">{t.alphaMining.metrics.totalReturn}</span>
                <span className={`text-lg font-bold ${
                  metrics.total_return > 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  {metrics.total_return > 0 ? '+' : ''}
                  {(metrics.total_return * 100).toFixed(2)}%
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 收益曲线 */}
      {returnsCurve && returnsCurve.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-500" />
              {t.alphaMining.metrics.returnsCurve}
            </CardTitle>
            <CardDescription>{t.alphaMining.metrics.returnsDesc}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={returnsCurve}>
                  <defs>
                    <linearGradient id="colorStrategy" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorBenchmark" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6b7280" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#6b7280" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey="date" 
                    tick={{ fontSize: 10 }}
                    tickFormatter={(value) => value.slice(5)}
                  />
                  <YAxis 
                    tick={{ fontSize: 10 }}
                    tickFormatter={(value) => `${(value * 100).toFixed(0)}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(255, 255, 255, 0.95)',
                      borderRadius: '8px',
                      border: '1px solid #e5e7eb',
                      fontSize: 12,
                    }}
                    formatter={(value: number, name: string) => [
                      `${(value * 100).toFixed(2)}%`,
                      name === 'strategy' ? t.alphaMining.metrics.strategy : t.alphaMining.metrics.benchmark
                    ]}
                  />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="strategy"
                    stroke="#10b981"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorStrategy)"
                    name={t.alphaMining.metrics.strategy}
                  />
                  <Area
                    type="monotone"
                    dataKey="benchmark"
                    stroke="#6b7280"
                    strokeWidth={1}
                    fillOpacity={1}
                    fill="url(#colorBenchmark)"
                    name={t.alphaMining.metrics.benchmark}
                    strokeDasharray="5 5"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 指标说明 */}
      <Card className="bg-gray-50">
        <CardContent className="py-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-gray-600">
            <div><strong>Sortino:</strong> {t.alphaMining.metrics.sortinoDesc}</div>
            <div><strong>Sharpe:</strong> {t.alphaMining.metrics.sharpeDesc}</div>
            <div><strong>IC:</strong> {t.alphaMining.metrics.icDesc}</div>
            <div><strong>Max DD:</strong> {t.alphaMining.metrics.maxDDDesc}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// 单个指标卡片
interface MetricCardProps {
  label: string;
  value: string;
  description: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down';
  good?: boolean;
}

const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  description,
  icon,
  trend,
  good,
}) => {
  return (
    <Card className={good ? 'border-green-200 bg-green-50/50' : ''}>
      <CardContent className="p-3">
        <div className="flex items-center gap-2 text-gray-500 mb-1">
          {icon}
          <span className="text-xs">{label}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className={`text-lg font-bold ${
            good ? 'text-green-600' : trend === 'down' ? 'text-red-600' : ''
          }`}>
            {value}
          </span>
          {trend === 'up' && <TrendingUp className="w-3 h-3 text-green-500" />}
          {trend === 'down' && <TrendingDown className="w-3 h-3 text-red-500" />}
        </div>
        <div className="text-xs text-gray-400 mt-0.5">{description}</div>
      </CardContent>
    </Card>
  );
};

// 归一化函数
function normalizeMetric(value: number, min: number, max: number): number {
  const normalized = ((value - min) / (max - min)) * 100;
  return Math.max(0, Math.min(100, normalized));
}

// 因子评级
function getFactorRating(metrics: FactorMetrics, t: any): {
  label: string;
  className: string;
  icon: React.ReactNode;
} {
  const score = 
    (metrics.sortino_ratio > 1 ? 25 : metrics.sortino_ratio > 0 ? 15 : 0) +
    (metrics.sharpe_ratio > 0.5 ? 25 : metrics.sharpe_ratio > 0 ? 15 : 0) +
    (Math.abs(metrics.ic) > 0.05 ? 25 : Math.abs(metrics.ic) > 0.03 ? 15 : 0) +
    (metrics.win_rate > 0.55 ? 25 : metrics.win_rate > 0.5 ? 15 : 0);

  if (score >= 80) {
    return {
      label: t.alphaMining.metrics.excellent,
      className: 'bg-green-100 text-green-700',
      icon: <TrendingUp className="w-3 h-3" />,
    };
  } else if (score >= 50) {
    return {
      label: t.alphaMining.metrics.good,
      className: 'bg-blue-100 text-blue-700',
      icon: <Activity className="w-3 h-3" />,
    };
  } else if (score >= 30) {
    return {
      label: t.alphaMining.metrics.average,
      className: 'bg-amber-100 text-amber-700',
      icon: <AlertTriangle className="w-3 h-3" />,
    };
  } else {
    return {
      label: t.alphaMining.metrics.poor,
      className: 'bg-red-100 text-red-700',
      icon: <TrendingDown className="w-3 h-3" />,
    };
  }
}

export default MetricsDashboard;
