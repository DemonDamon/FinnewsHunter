import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { agentApi } from '@/lib/api-client'
import {
  Bot,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  Trash2,
  Play,
  Zap,
  GitBranch,
  MessageSquare,
  TrendingUp,
  AlertCircle,
  ChevronRight,
  Workflow,
  ArrowRight,
  Timer,
} from 'lucide-react'
import type { AgentLogEntry, AgentMetrics, AgentInfo, WorkflowInfo } from '@/types/api'

// 状态徽章颜色
const statusColors: Record<string, { bg: string; text: string; border: string }> = {
  started: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-200' },
  completed: { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-200' },
  failed: { bg: 'bg-rose-100', text: 'text-rose-700', border: 'border-rose-200' },
  active: { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-200' },
  inactive: { bg: 'bg-gray-100', text: 'text-gray-700', border: 'border-gray-200' },
}

// 智能体图标映射
const agentIcons: Record<string, React.ReactNode> = {
  NewsAnalyst: <MessageSquare className="w-4 h-4" />,
  BullResearcher: <TrendingUp className="w-4 h-4" />,
  BearResearcher: <AlertCircle className="w-4 h-4" />,
  InvestmentManager: <Zap className="w-4 h-4" />,
  DebateWorkflow: <Workflow className="w-4 h-4" />,
}

// 格式化时间戳
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// 格式化相对时间
function formatRelativeTime(timestamp: string): string {
  const now = new Date()
  const date = new Date(timestamp)
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  
  if (diffSec < 60) return `${diffSec}秒前`
  if (diffMin < 60) return `${diffMin}分钟前`
  if (diffHour < 24) return `${diffHour}小时前`
  return formatTimestamp(timestamp)
}

export default function AgentMonitorPage() {
  const queryClient = useQueryClient()
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  // 获取性能指标
  const { data: metrics, isLoading: metricsLoading, refetch: refetchMetrics } = useQuery({
    queryKey: ['agent', 'metrics'],
    queryFn: agentApi.getMetrics,
    refetchInterval: autoRefresh ? 10000 : false, // 10秒自动刷新
    staleTime: 5000,
  })

  // 获取执行日志
  const { data: logs, isLoading: logsLoading, refetch: refetchLogs } = useQuery({
    queryKey: ['agent', 'logs', selectedAgent],
    queryFn: () => agentApi.getLogs({
      limit: 50,
      agent_name: selectedAgent || undefined,
    }),
    refetchInterval: autoRefresh ? 5000 : false, // 5秒自动刷新
    staleTime: 3000,
  })

  // 获取可用智能体
  const { data: available, isLoading: availableLoading } = useQuery({
    queryKey: ['agent', 'available'],
    queryFn: agentApi.getAvailable,
    staleTime: 60000, // 1分钟
  })

  // 清空日志 Mutation
  const clearLogsMutation = useMutation({
    mutationFn: agentApi.clearLogs,
    onSuccess: (data) => {
      toast.success(data.message)
      queryClient.invalidateQueries({ queryKey: ['agent', 'logs'] })
      queryClient.invalidateQueries({ queryKey: ['agent', 'metrics'] })
    },
    onError: (error: Error) => {
      toast.error(`清空失败: ${error.message}`)
    },
  })

  const handleRefresh = () => {
    refetchMetrics()
    refetchLogs()
    toast.success('数据已刷新')
  }

  const handleClearLogs = () => {
    if (window.confirm('确定要清空所有执行日志吗？此操作不可恢复。')) {
      clearLogsMutation.mutate()
    }
  }

  // 计算成功率
  const successRate = metrics
    ? ((metrics.successful_executions / metrics.total_executions) * 100 || 0).toFixed(1)
    : '0'

  return (
    <div className="p-6 space-y-6 bg-gradient-to-br from-slate-50 to-indigo-50 min-h-screen">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-gray-900 flex items-center gap-3">
            <Activity className="w-8 h-8 text-indigo-500" />
            智能体监控台
          </h1>
          <p className="text-muted-foreground mt-1">
            实时查看智能体执行状态、性能指标和思考链
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={autoRefresh ? 'bg-emerald-50 border-emerald-200' : ''}
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${autoRefresh ? 'animate-spin' : ''}`} />
            {autoRefresh ? '自动刷新中' : '自动刷新已关闭'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            手动刷新
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleClearLogs}
            className="text-rose-600 hover:bg-rose-50"
            disabled={clearLogsMutation.isPending}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            清空日志
          </Button>
        </div>
      </div>

      {/* 性能指标卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-white/80 backdrop-blur-sm border-indigo-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">总执行次数</p>
                <p className="text-3xl font-bold text-indigo-600">
                  {metrics?.total_executions || 0}
                </p>
              </div>
              <Play className="w-10 h-10 text-indigo-500/30" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white/80 backdrop-blur-sm border-emerald-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">成功执行</p>
                <p className="text-3xl font-bold text-emerald-600">
                  {metrics?.successful_executions || 0}
                </p>
              </div>
              <CheckCircle2 className="w-10 h-10 text-emerald-500/30" />
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              成功率 {successRate}%
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/80 backdrop-blur-sm border-rose-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">失败次数</p>
                <p className="text-3xl font-bold text-rose-600">
                  {metrics?.failed_executions || 0}
                </p>
              </div>
              <XCircle className="w-10 h-10 text-rose-500/30" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white/80 backdrop-blur-sm border-amber-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">平均耗时</p>
                <p className="text-3xl font-bold text-amber-600">
                  {metrics?.avg_execution_time?.toFixed(1) || 0}s
                </p>
              </div>
              <Clock className="w-10 h-10 text-amber-500/30" />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 智能体列表 */}
        <Card className="bg-white/90">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-indigo-500" />
              可用智能体
            </CardTitle>
            <CardDescription>
              系统中已注册的智能体和工作流
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* 智能体 */}
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">智能体</h4>
              <div className="space-y-2">
                {available?.agents.map((agent) => (
                  <div
                    key={agent.name}
                    className={`p-3 rounded-lg border cursor-pointer transition-all ${
                      selectedAgent === agent.name
                        ? 'border-indigo-300 bg-indigo-50'
                        : 'border-gray-100 hover:border-indigo-200 hover:bg-indigo-50/50'
                    }`}
                    onClick={() => setSelectedAgent(selectedAgent === agent.name ? null : agent.name)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                          agent.status === 'active' ? 'bg-emerald-100 text-emerald-600' : 'bg-gray-100 text-gray-600'
                        }`}>
                          {agentIcons[agent.name] || <Bot className="w-4 h-4" />}
                        </div>
                        <div>
                          <p className="font-medium text-gray-900 text-sm">{agent.name}</p>
                          <p className="text-xs text-gray-500">{agent.role}</p>
                        </div>
                      </div>
                      <Badge className={`${statusColors[agent.status].bg} ${statusColors[agent.status].text}`}>
                        {agent.status === 'active' ? '活跃' : '未激活'}
                      </Badge>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">{agent.description}</p>
                    {metrics?.agent_stats?.[agent.name] && (
                      <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                        <span>执行 {metrics.agent_stats[agent.name].total} 次</span>
                        <span>•</span>
                        <span>成功 {metrics.agent_stats[agent.name].successful}</span>
                        {metrics.agent_stats[agent.name].avg_time > 0 && (
                          <>
                            <span>•</span>
                            <span>平均 {metrics.agent_stats[agent.name].avg_time.toFixed(1)}s</span>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* 工作流 */}
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">工作流</h4>
              <div className="space-y-2">
                {available?.workflows.map((workflow) => (
                  <div
                    key={workflow.name}
                    className="p-3 rounded-lg border border-gray-100 hover:border-purple-200 hover:bg-purple-50/50 transition-all"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <GitBranch className="w-4 h-4 text-purple-500" />
                      <span className="font-medium text-gray-900 text-sm">{workflow.name}</span>
                    </div>
                    <p className="text-xs text-gray-500">{workflow.description}</p>
                    <div className="flex items-center gap-1 mt-2 flex-wrap">
                      {workflow.agents.map((agent, idx) => (
                        <span key={agent} className="flex items-center">
                          <Badge variant="outline" className="text-xs">
                            {agent}
                          </Badge>
                          {idx < workflow.agents.length - 1 && (
                            <ArrowRight className="w-3 h-3 text-gray-400 mx-1" />
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 执行日志 */}
        <Card className="lg:col-span-2 bg-white/90">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-500" />
                执行日志
                {selectedAgent && (
                  <Badge variant="outline" className="ml-2">
                    筛选: {selectedAgent}
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedAgent(null)
                      }}
                      className="ml-1 hover:text-rose-500"
                    >
                      ×
                    </button>
                  </Badge>
                )}
              </span>
              <span className="text-sm font-normal text-gray-500">
                {logs?.length || 0} 条记录
              </span>
            </CardTitle>
            <CardDescription>
              实时智能体执行日志和状态追踪
            </CardDescription>
          </CardHeader>
          <CardContent>
            {logsLoading ? (
              <div className="flex items-center justify-center py-12">
                <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
              </div>
            ) : logs && logs.length > 0 ? (
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
                {logs.map((log, index) => (
                  <div
                    key={log.id}
                    className={`p-3 rounded-lg border transition-all ${
                      log.status === 'completed'
                        ? 'border-emerald-100 bg-emerald-50/30'
                        : log.status === 'failed'
                        ? 'border-rose-100 bg-rose-50/30'
                        : 'border-blue-100 bg-blue-50/30'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                          log.status === 'completed'
                            ? 'bg-emerald-100 text-emerald-600'
                            : log.status === 'failed'
                            ? 'bg-rose-100 text-rose-600'
                            : 'bg-blue-100 text-blue-600'
                        }`}>
                          {log.status === 'completed' ? (
                            <CheckCircle2 className="w-4 h-4" />
                          ) : log.status === 'failed' ? (
                            <XCircle className="w-4 h-4" />
                          ) : (
                            <Play className="w-4 h-4" />
                          )}
                        </div>
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-gray-900">
                              {log.agent_name}
                            </span>
                            {log.agent_role && (
                              <span className="text-xs text-gray-500">
                                ({log.agent_role})
                              </span>
                            )}
                            <Badge className={`${statusColors[log.status].bg} ${statusColors[log.status].text} text-xs`}>
                              {log.status === 'completed' ? '完成' : log.status === 'failed' ? '失败' : '进行中'}
                            </Badge>
                          </div>
                          <p className="text-sm text-gray-600 mt-1">
                            {log.action.replace(/_/g, ' ')}
                          </p>
                          {log.details && Object.keys(log.details).length > 0 && (
                            <div className="mt-2 text-xs text-gray-500 bg-gray-50 p-2 rounded">
                              {Object.entries(log.details).map(([key, value]) => (
                                <div key={key} className="flex gap-2">
                                  <span className="font-medium">{key}:</span>
                                  <span>{String(value)}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <p className="text-xs text-gray-400">
                          {formatRelativeTime(log.timestamp)}
                        </p>
                        {log.execution_time && (
                          <p className="text-xs text-gray-500 flex items-center gap-1 mt-1">
                            <Timer className="w-3 h-3" />
                            {log.execution_time.toFixed(1)}s
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500">
                <Activity className="w-16 h-16 mx-auto opacity-30 mb-4" />
                <p className="text-lg">暂无执行日志</p>
                <p className="text-sm mt-2">
                  执行分析任务或辩论后，日志将在此显示
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 最近活动时间线 */}
      {metrics?.recent_activity && metrics.recent_activity.length > 0 && (
        <Card className="bg-white/90">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-purple-500" />
              最近活动
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 overflow-x-auto pb-2">
              {metrics.recent_activity.map((activity, index) => (
                <div
                  key={index}
                  className={`flex-shrink-0 px-3 py-2 rounded-lg border ${statusColors[activity.status]?.bg} ${statusColors[activity.status]?.border}`}
                >
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${
                      activity.status === 'completed' ? 'bg-emerald-500' :
                      activity.status === 'failed' ? 'bg-rose-500' : 'bg-blue-500'
                    }`} />
                    <span className="text-sm font-medium">{activity.agent_name}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {activity.action.replace(/_/g, ' ')}
                  </p>
                  <p className="text-xs text-gray-400">
                    {formatRelativeTime(activity.timestamp)}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
