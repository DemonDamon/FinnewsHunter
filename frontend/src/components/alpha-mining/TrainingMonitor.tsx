/**
 * 训练进度实时监控组件
 * 
 * 使用 SSE 订阅训练进度，实时显示：
 * - 训练步数/进度
 * - Loss/Reward 曲线
 * - 当前最优因子表达式
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, Legend, ReferenceLine 
} from 'recharts';
import { 
  Play, Square, RefreshCw, Activity, 
  TrendingUp, Zap, CheckCircle2, AlertCircle 
} from 'lucide-react';
import { useGlobalI18n } from '@/store/useLanguageStore';

interface TrainingMetrics {
  step: number;
  progress: number;
  loss: number;
  avg_reward: number;
  max_reward: number;
  valid_ratio: number;
  best_score: number;
  best_formula: string;
}

interface TrainingMonitorProps {
  apiBaseUrl?: string;
  onTrainingComplete?: (result: { best_score: number; best_formula: string }) => void;
}

type TrainingStatus = 'idle' | 'running' | 'completed' | 'error';

const TrainingMonitor: React.FC<TrainingMonitorProps> = ({
  apiBaseUrl = '/api/v1',
  onTrainingComplete,
}) => {
  const t = useGlobalI18n();
  const [status, setStatus] = useState<TrainingStatus>('idle');
  const [progress, setProgress] = useState(0);
  const [currentMetrics, setCurrentMetrics] = useState<TrainingMetrics | null>(null);
  const [history, setHistory] = useState<TrainingMetrics[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [numSteps, setNumSteps] = useState(100);
  const [useSentiment, setUseSentiment] = useState(true);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 开始训练
  const startTraining = useCallback(async () => {
    setStatus('running');
    setProgress(0);
    setHistory([]);
    setError(null);
    setCurrentMetrics(null);

    try {
      // 使用 fetch + SSE
      abortControllerRef.current = new AbortController();
      
      const response = await fetch(`${apiBaseUrl}/alpha-mining/mine/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          num_steps: numSteps,
          use_sentiment: useSentiment,
          batch_size: 16,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7);
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6);
          } else if (line === '' && currentEvent && currentData) {
            try {
              const data = JSON.parse(currentData);
              handleSSEEvent(currentEvent, data);
            } catch (e) {
              console.error('Failed to parse SSE data:', currentData);
            }
            currentEvent = '';
            currentData = '';
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Training error:', err);
        setError(err.message || t.alphaMining.training.trainingFailed);
        setStatus('error');
      }
    }
  }, [apiBaseUrl, numSteps, useSentiment]);

  // 处理 SSE 事件
  const handleSSEEvent = useCallback((event: string, data: any) => {
    switch (event) {
      case 'start':
        console.log('Training started:', data);
        break;
        
      case 'progress':
        const metrics: TrainingMetrics = {
          step: data.step,
          progress: data.progress,
          loss: data.loss,
          avg_reward: data.avg_reward,
          max_reward: data.max_reward,
          valid_ratio: data.valid_ratio,
          best_score: data.best_score,
          best_formula: data.best_formula,
        };
        setCurrentMetrics(metrics);
        setProgress(data.progress);
        setHistory(prev => [...prev, metrics]);
        break;
        
      case 'complete':
        setStatus('completed');
        setProgress(100);
        onTrainingComplete?.({
          best_score: data.best_score,
          best_formula: data.best_formula,
        });
        break;
        
      case 'error':
        setError(data.error);
        setStatus('error');
        break;
    }
  }, [onTrainingComplete]);

  // 停止训练
  const stopTraining = useCallback(() => {
    abortControllerRef.current?.abort();
    eventSourceRef.current?.close();
    setStatus('idle');
  }, []);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      eventSourceRef.current?.close();
    };
  }, []);

  // 状态颜色映射
  const statusConfig = {
    idle: { color: 'bg-gray-100 text-gray-600', icon: <Activity className="w-4 h-4" /> },
    running: { color: 'bg-blue-100 text-blue-600', icon: <RefreshCw className="w-4 h-4 animate-spin" /> },
    completed: { color: 'bg-green-100 text-green-600', icon: <CheckCircle2 className="w-4 h-4" /> },
    error: { color: 'bg-red-100 text-red-600', icon: <AlertCircle className="w-4 h-4" /> },
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-amber-500" />
              {t.alphaMining.training.title}
            </CardTitle>
            <CardDescription>
              {t.alphaMining.training.desc}
            </CardDescription>
          </div>
          <Badge className={statusConfig[status].color}>
            {statusConfig[status].icon}
            <span className="ml-1">
              {status === 'idle' && t.alphaMining.training.ready}
              {status === 'running' && t.alphaMining.training.running}
              {status === 'completed' && t.alphaMining.training.completed}
              {status === 'error' && t.alphaMining.training.error}
            </span>
          </Badge>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* 控制面板 */}
        <div className="flex flex-wrap items-center gap-4 p-4 bg-gray-50 rounded-lg">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium">{t.alphaMining.training.steps}:</label>
            <input
              type="number"
              value={numSteps}
              onChange={(e) => setNumSteps(Number(e.target.value))}
              min={10}
              max={1000}
              disabled={status === 'running'}
              className="w-24 px-2 py-1 border rounded text-sm"
            />
          </div>
          
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="useSentiment"
              checked={useSentiment}
              onChange={(e) => setUseSentiment(e.target.checked)}
              disabled={status === 'running'}
              className="rounded"
            />
            <label htmlFor="useSentiment" className="text-sm">
              {t.alphaMining.training.useSentiment}
            </label>
          </div>
          
          <div className="flex-1" />
          
          {status === 'running' ? (
            <Button variant="destructive" size="sm" onClick={stopTraining}>
              <Square className="w-4 h-4 mr-1" />
              {t.alphaMining.training.stop}
            </Button>
          ) : (
            <Button onClick={startTraining} disabled={status !== 'idle'}>
              <Play className="w-4 h-4 mr-1" />
              {t.alphaMining.training.start}
            </Button>
          )}
        </div>

        {/* 进度条 */}
        <div className="space-y-1">
          <div className="flex justify-between text-sm">
            <span>{t.alphaMining.training.progress}</span>
            <span>{progress.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          {currentMetrics && (
            <div className="text-xs text-gray-500">
              Step {currentMetrics.step} / {numSteps}
            </div>
          )}
        </div>

        {/* 实时指标 */}
        {currentMetrics && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label="Loss" value={currentMetrics.loss.toFixed(4)} trend="down" />
            <MetricCard label="Avg Reward" value={currentMetrics.avg_reward.toFixed(4)} trend="up" />
            <MetricCard label="Best Score" value={currentMetrics.best_score.toFixed(4)} trend="up" highlight />
            <MetricCard label="Valid Ratio" value={`${(currentMetrics.valid_ratio * 100).toFixed(1)}%`} />
          </div>
        )}

        {/* 当前最优因子 */}
        {currentMetrics?.best_formula && (
          <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200">
            <div className="text-xs text-emerald-600 font-medium mb-1">{t.alphaMining.training.bestFactor}</div>
            <code className="text-sm font-mono text-emerald-800">
              {currentMetrics.best_formula}
            </code>
          </div>
        )}

        {/* 收敛曲线 */}
        {history.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium">{t.alphaMining.training.convergence}</h4>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey="step" 
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Step', position: 'bottom', fontSize: 12 }}
                  />
                  <YAxis 
                    yAxisId="left"
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Reward', angle: -90, position: 'insideLeft', fontSize: 12 }}
                  />
                  <YAxis 
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Loss', angle: 90, position: 'insideRight', fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(255, 255, 255, 0.95)',
                      borderRadius: '8px',
                      border: '1px solid #e5e7eb',
                      fontSize: 12,
                    }}
                  />
                  <Legend />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="avg_reward"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={false}
                    name="Avg Reward"
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="best_score"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={false}
                    name="Best Score"
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="loss"
                    stroke="#ef4444"
                    strokeWidth={1}
                    dot={false}
                    name="Loss"
                    strokeDasharray="5 5"
                  />
                  <ReferenceLine yAxisId="left" y={0} stroke="#666" strokeDasharray="3 3" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* 错误信息 */}
        {error && (
          <div className="p-3 bg-red-50 rounded-lg border border-red-200">
            <div className="text-sm text-red-600">{error}</div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// 指标卡片组件
interface MetricCardProps {
  label: string;
  value: string;
  trend?: 'up' | 'down';
  highlight?: boolean;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, trend, highlight }) => {
  return (
    <div className={`p-3 rounded-lg ${highlight ? 'bg-amber-50 border border-amber-200' : 'bg-gray-50'}`}>
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-lg font-semibold flex items-center gap-1 ${highlight ? 'text-amber-600' : ''}`}>
        {value}
        {trend === 'up' && <TrendingUp className="w-3 h-3 text-green-500" />}
        {trend === 'down' && <TrendingUp className="w-3 h-3 text-red-500 rotate-180" />}
      </div>
    </div>
  );
};

export default TrainingMonitor;
