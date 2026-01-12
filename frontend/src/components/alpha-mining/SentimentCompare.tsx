/**
 * 情感融合效果对比组件
 * 
 * 对比纯技术因子 vs 情感增强因子的效果：
 * - 左右两栏对比
 * - 指标对比条形图
 * - 改进幅度高亮
 */

import React, { useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell, ReferenceLine
} from 'recharts';
import {
  Play, Heart, Cpu, TrendingUp, TrendingDown,
  ArrowRight, Loader2, Sparkles
} from 'lucide-react';
import { useGlobalI18n } from '@/store/useLanguageStore';

interface CompareResult {
  best_score: number;
  best_formula: string;
  total_steps: number;
  num_features: number;
}

interface SentimentCompareProps {
  apiBaseUrl?: string;
}

const SentimentCompare: React.FC<SentimentCompareProps> = ({
  apiBaseUrl = '/api/v1',
}) => {
  const t = useGlobalI18n();
  const [loading, setLoading] = useState(false);
  const [withSentiment, setWithSentiment] = useState<CompareResult | null>(null);
  const [withoutSentiment, setWithoutSentiment] = useState<CompareResult | null>(null);
  const [improvement, setImprovement] = useState<{ score_diff: number; improvement_pct: number } | null>(null);
  const [numSteps, setNumSteps] = useState(50);
  const [error, setError] = useState<string | null>(null);

  // 执行对比
  const runComparison = useCallback(async () => {
    setLoading(true);
    setError(null);
    setWithSentiment(null);
    setWithoutSentiment(null);
    setImprovement(null);

    try {
      const response = await fetch(`${apiBaseUrl}/alpha-mining/compare-sentiment`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          num_steps: numSteps,
          batch_size: 16,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      if (data.success) {
        setWithSentiment(data.with_sentiment);
        setWithoutSentiment(data.without_sentiment);
        setImprovement(data.improvement);
      } else {
        throw new Error(t.alphaMining.sentiment.comparisonFailed);
      }
    } catch (err: any) {
      console.error('Comparison error:', err);
      setError(err.message || t.alphaMining.sentiment.comparisonFailed);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, numSteps]);

  // 对比条形图数据
  const chartData = withSentiment && withoutSentiment ? [
    {
      name: 'Best Score',
      without: withoutSentiment.best_score,
      with: withSentiment.best_score,
    },
    {
      name: 'Features',
      without: withoutSentiment.num_features,
      with: withSentiment.num_features,
    },
  ] : [];

  // 改进幅度是否为正
  const isImproved = improvement && improvement.score_diff > 0;

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-purple-500" />
              {t.alphaMining.sentiment.title}
            </CardTitle>
            <CardDescription>
              {t.alphaMining.sentiment.desc}
            </CardDescription>
          </div>
          {improvement && (
            <Badge className={isImproved ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
              {isImproved ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
              {isImproved ? '+' : ''}{improvement.improvement_pct.toFixed(1)}%
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* 控制面板 */}
        <div className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium">{t.alphaMining.sentiment.steps}:</label>
            <input
              type="number"
              value={numSteps}
              onChange={(e) => setNumSteps(Number(e.target.value))}
              min={20}
              max={200}
              disabled={loading}
              className="w-20 px-2 py-1 border rounded text-sm"
            />
          </div>
          <div className="flex-1" />
          <Button onClick={runComparison} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                {t.alphaMining.sentiment.comparing}
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-1" />
                {t.alphaMining.sentiment.start}
              </>
            )}
          </Button>
        </div>

        {/* 对比结果 */}
        {withSentiment && withoutSentiment && (
          <>
            {/* 左右对比卡片 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 纯技术因子 */}
              <Card className="border-blue-200 bg-blue-50/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2 text-blue-700">
                    <Cpu className="w-4 h-4" />
                    {t.alphaMining.sentiment.techOnly}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {withoutSentiment.num_features}{t.alphaMining.sentiment.techDesc}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div>
                      <div className="text-xs text-gray-500">{t.alphaMining.sentiment.bestFactor}</div>
                      <code className="text-sm font-mono block mt-1 p-2 bg-white rounded border truncate">
                        {withoutSentiment.best_formula || t.alphaMining.sentiment.none}
                      </code>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Best Score</span>
                      <span className="text-lg font-bold text-blue-600">
                        {withoutSentiment.best_score.toFixed(4)}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* 情感增强因子 */}
              <Card className="border-emerald-200 bg-emerald-50/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2 text-emerald-700">
                    <Heart className="w-4 h-4" />
                    {t.alphaMining.sentiment.enhanced}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {withSentiment.num_features}{t.alphaMining.sentiment.enhancedDesc}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div>
                      <div className="text-xs text-gray-500">{t.alphaMining.sentiment.bestFactor}</div>
                      <code className="text-sm font-mono block mt-1 p-2 bg-white rounded border truncate">
                        {withSentiment.best_formula || t.alphaMining.sentiment.none}
                      </code>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-gray-600">Best Score</span>
                      <span className="text-lg font-bold text-emerald-600">
                        {withSentiment.best_score.toFixed(4)}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* 改进幅度 */}
            {improvement && (
              <Card className={isImproved ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}>
                <CardContent className="py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-full ${isImproved ? 'bg-green-100' : 'bg-red-100'}`}>
                        {isImproved ? (
                          <TrendingUp className="w-5 h-5 text-green-600" />
                        ) : (
                          <TrendingDown className="w-5 h-5 text-red-600" />
                        )}
                      </div>
                      <div>
                        <div className="text-sm font-medium">
                          {isImproved ? t.alphaMining.sentiment.improved : t.alphaMining.sentiment.degraded}
                        </div>
                        <div className="text-xs text-gray-500">
                          {t.alphaMining.sentiment.scoreDiff}: {improvement.score_diff > 0 ? '+' : ''}{improvement.score_diff.toFixed(6)}
                        </div>
                      </div>
                    </div>
                    <div className={`text-3xl font-bold ${isImproved ? 'text-green-600' : 'text-red-600'}`}>
                      {isImproved ? '+' : ''}{improvement.improvement_pct.toFixed(1)}%
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 对比条形图 */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">{t.alphaMining.sentiment.comparison}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={[{
                        name: 'Best Score',
                        [t.alphaMining.sentiment.techOnlyBar]: withoutSentiment.best_score,
                        [t.alphaMining.sentiment.enhancedBar]: withSentiment.best_score,
                      }]}
                      layout="vertical"
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis type="number" tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={80} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'rgba(255, 255, 255, 0.95)',
                          borderRadius: '8px',
                          border: '1px solid #e5e7eb',
                          fontSize: 12,
                        }}
                        formatter={(value: number) => value.toFixed(4)}
                      />
                      <Legend />
                      <Bar dataKey={t.alphaMining.sentiment.techOnlyBar} fill="#3b82f6" radius={[0, 4, 4, 0]} />
                      <Bar dataKey={t.alphaMining.sentiment.enhancedBar} fill="#10b981" radius={[0, 4, 4, 0]} />
                      <ReferenceLine x={0} stroke="#666" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* 结论 */}
            <div className="p-4 bg-gray-50 rounded-lg text-sm text-gray-600">
              <strong>{t.alphaMining.sentiment.conclusion}</strong>
              {isImproved ? (
                <>
                  {t.alphaMining.sentiment.conclusionPositive}
                </>
              ) : (
                <>
                  {t.alphaMining.sentiment.conclusionNegative}
                </>
              )}
            </div>
          </>
        )}

        {/* 加载状态 */}
        {loading && (
          <div className="py-12 text-center">
            <Loader2 className="w-8 h-8 animate-spin mx-auto text-purple-500 mb-3" />
            <p className="text-sm text-gray-500">{t.alphaMining.sentiment.comparingText}</p>
            <p className="text-xs text-gray-400 mt-1">
              {t.alphaMining.sentiment.comparingHint} {numSteps} {t.alphaMining.sentiment.stepsText}
            </p>
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="p-4 bg-red-50 rounded-lg border border-red-200">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {/* 初始状态 */}
        {!loading && !withSentiment && !error && (
          <div className="py-12 text-center text-gray-500">
            <Sparkles className="w-12 h-12 mx-auto opacity-50 mb-3" />
            <p>{t.alphaMining.sentiment.startHint}</p>
            <p className="text-sm mt-1">
              {t.alphaMining.sentiment.startDesc}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default SentimentCompare;
