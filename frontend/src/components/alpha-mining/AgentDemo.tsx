/**
 * AgenticX Agent 调用演示组件
 * 
 * 展示如何通过 Agent 接口调用 AlphaMiningTool：
 * - Agent 调用流程可视化
 * - Tool 参数输入面板
 * - 执行日志流式显示
 */

import React, { useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bot, Wrench, Play, CheckCircle2, XCircle,
  Clock, ArrowRight, Terminal, Loader2, Code
} from 'lucide-react';
import { useGlobalI18n } from '@/store/useLanguageStore';

interface AgentDemoResult {
  success: boolean;
  agent_name: string;
  tool_name: string;
  input_params: Record<string, any>;
  output: Record<string, any> | null;
  execution_time: number;
  logs: string[];
}

interface AgentDemoProps {
  apiBaseUrl?: string;
}

const AgentDemo: React.FC<AgentDemoProps> = ({
  apiBaseUrl = '/api/v1',
}) => {
  const t = useGlobalI18n();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgentDemoResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // 参数
  const [stockCode, setStockCode] = useState('SH600519');
  const [numSteps, setNumSteps] = useState(30);
  const [useSentiment, setUseSentiment] = useState(true);
  
  // 执行演示
  const runDemo = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${apiBaseUrl}/alpha-mining/agent-demo`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          stock_code: stockCode || null,
          num_steps: numSteps,
          use_sentiment: useSentiment,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      console.error('Agent demo error:', err);
      setError(err.message || t.alphaMining.agent.executeFailed);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, stockCode, numSteps, useSentiment]);

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-indigo-500" />
              {t.alphaMining.agent.title}
            </CardTitle>
            <CardDescription>
              {t.alphaMining.agent.desc}
            </CardDescription>
          </div>
          {result && (
            <Badge className={result.success ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
              {result.success ? <CheckCircle2 className="w-3 h-3 mr-1" /> : <XCircle className="w-3 h-3 mr-1" />}
              {result.success ? t.alphaMining.agent.success : t.alphaMining.agent.failed}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* 调用流程图 */}
        <div className="flex items-center justify-center gap-2 p-4 bg-gradient-to-r from-indigo-50 to-purple-50 rounded-lg">
          <FlowNode icon={<Bot className="w-5 h-5" />} label="QuantitativeAgent" active={loading} />
          <ArrowRight className="w-4 h-4 text-gray-400" />
          <FlowNode icon={<Wrench className="w-5 h-5" />} label="AlphaMiningTool" active={loading} />
          <ArrowRight className="w-4 h-4 text-gray-400" />
          <FlowNode icon={<Code className="w-5 h-5" />} label="AlphaTrainer" active={loading} />
        </div>

        {/* 参数输入面板 */}
        <Card className="bg-gray-50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Wrench className="w-4 h-4 text-gray-500" />
              {t.alphaMining.agent.toolParams}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">
                  {t.alphaMining.agent.stockCode}
                </label>
                <input
                  type="text"
                  value={stockCode}
                  onChange={(e) => setStockCode(e.target.value)}
                  placeholder={t.alphaMining.agent.stockPlaceholder}
                  disabled={loading}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">
                  {t.alphaMining.agent.steps}
                </label>
                <input
                  type="number"
                  value={numSteps}
                  onChange={(e) => setNumSteps(Number(e.target.value))}
                  min={10}
                  max={100}
                  disabled={loading}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useSentiment}
                    onChange={(e) => setUseSentiment(e.target.checked)}
                    disabled={loading}
                    className="rounded"
                  />
                  <span className="text-sm">{t.alphaMining.agent.useSentiment}</span>
                </label>
              </div>
            </div>
            
            <div className="mt-4 flex justify-end">
              <Button onClick={runDemo} disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                    {t.alphaMining.agent.executing}
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-1" />
                    {t.alphaMining.agent.execute}
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* 执行结果 */}
        <AnimatePresence>
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="space-y-4"
            >
              {/* Agent & Tool 信息 */}
              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                      <Bot className="w-4 h-4" />
                      Agent
                    </div>
                    <div className="font-medium">{result.agent_name}</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4">
                    <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
                      <Wrench className="w-4 h-4" />
                      Tool
                    </div>
                    <div className="font-medium">{result.tool_name}</div>
                  </CardContent>
                </Card>
              </div>

              {/* 输入参数 */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">{t.alphaMining.agent.inputParams}</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="text-xs bg-gray-900 text-green-400 p-3 rounded-md overflow-x-auto">
                    {JSON.stringify(result.input_params, null, 2)}
                  </pre>
                </CardContent>
              </Card>

              {/* 输出结果 */}
              {result.output && (
                <Card className="border-green-200 bg-green-50/50">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2 text-green-700">
                      <CheckCircle2 className="w-4 h-4" />
                      {t.alphaMining.agent.output}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-3 gap-4 mb-3">
                      <div className="text-center p-3 bg-white rounded-lg">
                        <div className="text-xs text-gray-500">Best Score</div>
                        <div className="text-lg font-bold text-green-600">
                          {result.output.best_score?.toFixed(4) || '--'}
                        </div>
                      </div>
                      <div className="text-center p-3 bg-white rounded-lg">
                        <div className="text-xs text-gray-500">Total Steps</div>
                        <div className="text-lg font-bold">
                          {result.output.total_steps || '--'}
                        </div>
                      </div>
                      <div className="text-center p-3 bg-white rounded-lg">
                        <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
                          <Clock className="w-3 h-3" />
                          {t.alphaMining.agent.executionTime}
                        </div>
                        <div className="text-lg font-bold">
                          {result.execution_time}s
                        </div>
                      </div>
                    </div>
                    {result.output.best_formula && (
                      <div className="p-3 bg-white rounded-lg">
                        <div className="text-xs text-gray-500 mb-1">{t.alphaMining.agent.bestFactor}</div>
                        <code className="text-sm font-mono text-emerald-700">
                          {result.output.best_formula}
                        </code>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* 执行日志 */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-gray-500" />
                    {t.alphaMining.agent.logs}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="bg-gray-900 rounded-md p-3 max-h-48 overflow-y-auto">
                    {result.logs.map((log, idx) => (
                      <motion.div
                        key={idx}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.1 }}
                        className="text-xs font-mono text-gray-300 mb-1"
                      >
                        <span className="text-gray-500">{idx + 1}.</span> {log}
                      </motion.div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* 代码示例 */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Code className="w-4 h-4 text-gray-500" />
                    {t.alphaMining.agent.codeExample}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="text-xs bg-gray-900 text-gray-300 p-3 rounded-md overflow-x-auto">
{`from agenticx.agents import QuantitativeAgent
from finnews.alpha_mining.tools import AlphaMiningTool

# ${t.alphaMining.agent.createAgent || 'Create Agent'}
agent = QuantitativeAgent(name="Quant")

# ${t.alphaMining.agent.registerTool || 'Register Tool'}
agent.register_tool(AlphaMiningTool())

# ${t.alphaMining.agent.executeMining || 'Execute factor mining'}
result = await agent.run(
    task="${t.alphaMining.agent.miningTask.replace('{code}', stockCode || 'SH600519')}",
    tools=["alpha_mining"],
    params={
        "num_steps": ${numSteps},
        "use_sentiment": ${useSentiment}
    }
)

print(f"Best Factor: {result.best_formula}")
print(f"Score: {result.best_score}")`}
                  </pre>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 错误提示 */}
        {error && (
          <div className="p-4 bg-red-50 rounded-lg border border-red-200">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {/* 初始状态 */}
        {!loading && !result && !error && (
          <div className="py-8 text-center text-gray-500">
            <Bot className="w-12 h-12 mx-auto opacity-50 mb-3" />
            <p>{t.alphaMining.agent.startHint}</p>
            <p className="text-sm mt-1">
              {t.alphaMining.agent.startDesc}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// 流程节点组件
interface FlowNodeProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
}

const FlowNode: React.FC<FlowNodeProps> = ({ icon, label, active }) => {
  return (
    <div className={`
      flex flex-col items-center p-3 rounded-lg transition-all
      ${active ? 'bg-indigo-100 ring-2 ring-indigo-400' : 'bg-white'}
    `}>
      <div className={`
        p-2 rounded-full mb-1
        ${active ? 'bg-indigo-500 text-white' : 'bg-gray-100 text-gray-600'}
      `}>
        {active ? <Loader2 className="w-5 h-5 animate-spin" /> : icon}
      </div>
      <span className="text-xs font-medium text-gray-700">{label}</span>
    </div>
  );
};

export default AgentDemo;
