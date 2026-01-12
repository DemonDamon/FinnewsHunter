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
import { useGlobalI18n, useLanguageStore } from '@/store/useLanguageStore'
import { formatRelativeTime as formatRelativeTimeUtil } from '@/lib/utils'

// 智能体角色和描述映射
const AGENT_ROLES: Record<string, { roleZh: string; roleEn: string; descZh: string; descEn: string }> = {
  NewsAnalyst: {
    roleZh: '金融新闻分析师',
    roleEn: 'Financial News Analyst',
    descZh: '分析金融新闻的情感、影响和关键信息',
    descEn: 'Analyzes sentiment, impact and key information of financial news',
  },
  BullResearcher: {
    roleZh: '看多研究员',
    roleEn: 'Bull Researcher',
    descZh: '从积极角度分析股票,发现投资机会',
    descEn: 'Analyzes stocks from a positive perspective, discovering investment opportunities',
  },
  BearResearcher: {
    roleZh: '看空研究员',
    roleEn: 'Bear Researcher',
    descZh: '从风险角度分析股票,识别潜在问题',
    descEn: 'Analyzes stocks from a risk perspective, identifying potential problems',
  },
  InvestmentManager: {
    roleZh: '投资经理',
    roleEn: 'Investment Manager',
    descZh: '综合多方观点,做出投资决策',
    descEn: 'Integrates multiple viewpoints to make investment decisions',
  },
  SearchAnalyst: {
    roleZh: '搜索分析师',
    roleEn: 'Search Analyst',
    descZh: '动态获取数据,支持 AkShare、BochaAI、网页搜索等',
    descEn: 'Dynamically obtains data, supports AkShare, BochaAI, web search, etc.',
  },
}

// 工作流描述映射
const WORKFLOW_DESCRIPTIONS: Record<string, { descZh: string; descEn: string }> = {
  NewsAnalysisWorkflow: {
    descZh: '新闻分析工作流：爬取 -> 清洗 -> 情感分析',
    descEn: 'News Analysis Workflow: Crawl -> Clean -> Sentiment Analysis',
  },
  InvestmentDebateWorkflow: {
    descZh: '投资辩论工作流：Bull vs Bear 多智能体辩论',
    descEn: 'Investment Debate Workflow: Bull vs Bear Multi-Agent Debate',
  },
}

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
// 格式化时间戳（已废弃，使用 formatRelativeTimeUtil）
function formatTimestamp(timestamp: string, locale: string = 'zh-CN'): string {
  const date = new Date(timestamp)
  return date.toLocaleString(locale, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export default function AgentMonitorPage() {
  const t = useGlobalI18n()
  const { lang } = useLanguageStore()
  const queryClient = useQueryClient()
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  
  // 获取智能体角色和描述（国际化）
  const getAgentInfo = (agentName: string, defaultRole: string, defaultDesc: string) => {
    const agentInfo = AGENT_ROLES[agentName]
    if (agentInfo) {
      return {
        role: lang === 'zh' ? agentInfo.roleZh : agentInfo.roleEn,
        description: lang === 'zh' ? agentInfo.descZh : agentInfo.descEn,
      }
    }
    return {
      role: defaultRole,
      description: defaultDesc,
    }
  }
  
  // 获取工作流描述（国际化）
  const getWorkflowDescription = (workflowName: string, defaultDesc: string) => {
    const workflowInfo = WORKFLOW_DESCRIPTIONS[workflowName]
    if (workflowInfo) {
      return lang === 'zh' ? workflowInfo.descZh : workflowInfo.descEn
    }
    return defaultDesc
  }

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
    if (window.confirm(t.agents.confirmClearLogs)) {
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
            {t.agents.title}
          </h1>
          <p className="text-muted-foreground mt-1">
            {t.agents.subtitle}
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
            {autoRefresh ? t.agents.autoRefreshing : t.agents.autoRefreshing}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            {t.agents.refresh}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleClearLogs}
            className="text-rose-600 hover:bg-rose-50"
            disabled={clearLogsMutation.isPending}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            {t.agents.clearLogs}
          </Button>
        </div>
      </div>

      {/* 性能指标卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-white/80 backdrop-blur-sm border-indigo-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">{t.agents.totalExec}</p>
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
                <p className="text-sm text-muted-foreground">{t.agents.successExec}</p>
                <p className="text-3xl font-bold text-emerald-600">
                  {metrics?.successful_executions || 0}
                </p>
              </div>
              <CheckCircle2 className="w-10 h-10 text-emerald-500/30" />
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              {t.agents.successRate} {successRate}%
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/80 backdrop-blur-sm border-rose-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">{t.agents.failedExec}</p>
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
                <p className="text-sm text-muted-foreground">{t.agents.avgTime}</p>
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
              {t.agents.availableAgents}
            </CardTitle>
            <CardDescription>
              {t.agents.availableAgentsDesc}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* 智能体 */}
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-2">{t.agents.agents}</h4>
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
                          <p className="text-xs text-gray-500">{getAgentInfo(agent.name, agent.role, agent.description).role}</p>
                        </div>
                      </div>
                      <Badge className={`${statusColors[agent.status].bg} ${statusColors[agent.status].text}`}>
                        {agent.status === 'active' ? t.agents.active : t.agents.inactive}
                      </Badge>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">{getAgentInfo(agent.name, agent.role, agent.description).description}</p>
                    {metrics?.agent_stats?.[agent.name] && (
                      <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                        <span>{t.agents.execTimes} {metrics.agent_stats[agent.name].total} {t.agents.times}</span>
                        <span>•</span>
                        <span>{t.agents.success} {metrics.agent_stats[agent.name].successful}</span>
                        {metrics.agent_stats[agent.name].avg_time > 0 && (
                          <>
                            <span>•</span>
                            <span>{t.agents.avg} {metrics.agent_stats[agent.name].avg_time.toFixed(1)}s</span>
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
              <h4 className="text-sm font-medium text-gray-500 mb-2">{t.agents.workflows}</h4>
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
                    <p className="text-xs text-gray-500">{getWorkflowDescription(workflow.name, workflow.description)}</p>
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
                {t.agents.execLogs}
                {selectedAgent && (
                  <Badge variant="outline" className="ml-2">
                    {selectedAgent}
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
                {logs?.length || 0} {t.agents.records}
              </span>
            </CardTitle>
            <CardDescription>
              {t.agents.execLogsDesc}
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
                                ({getAgentInfo(log.agent_name || '', log.agent_role, '').role})
                              </span>
                            )}
                            <Badge className={`${statusColors[log.status].bg} ${statusColors[log.status].text} text-xs`}>
                              {log.status === 'completed' ? t.tasks.completed : log.status === 'failed' ? t.tasks.failed : t.tasks.running}
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
                          {formatRelativeTimeUtil(log.timestamp, t.time)}
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
                <p className="text-lg">{t.agents.noLogs}</p>
                <p className="text-sm mt-2">
                  {t.agents.noLogsHint}
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
              {t.agents.recentActivity || 'Recent Activity'}
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
                    {formatRelativeTimeUtil(activity.timestamp, t.time)}
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
