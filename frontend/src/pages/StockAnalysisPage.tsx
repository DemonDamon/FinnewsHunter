import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { stockApi, agentApi } from '@/lib/api-client'
import { formatRelativeTime } from '@/lib/utils'
import NewsDetailDrawer from '@/components/NewsDetailDrawer'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Newspaper,
  BarChart3,
  MessageSquare,
  RefreshCw,
  Calendar,
  Swords,
  Bot,
  ThumbsUp,
  ThumbsDown,
  Scale,
  Loader2,
  Activity,
  ArrowLeft,
  Download,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Bar,
  Legend,
  ComposedChart,
  Line,
} from 'recharts'
import KLineChart from '@/components/KLineChart'
import type { DebateResponse } from '@/types/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 从代码中提取纯数字代码
const extractCode = (fullCode: string): string => {
  const code = fullCode.toUpperCase()
  if (code.startsWith('SH') || code.startsWith('SZ')) {
    return code.slice(2)
  }
  return code
}

// K线周期配置
type KLinePeriod = 'daily' | '1m' | '5m' | '15m' | '30m' | '60m'
const PERIOD_OPTIONS: { value: KLinePeriod; label: string; limit: number }[] = [
  { value: 'daily', label: '日K', limit: 180 },  // 约半年数据
  { value: '60m', label: '60分', limit: 200 },
  { value: '30m', label: '30分', limit: 200 },
  { value: '15m', label: '15分', limit: 200 },
  { value: '5m', label: '5分', limit: 300 },
  { value: '1m', label: '1分', limit: 400 },
]

// 定向爬取任务状态类型
type CrawlTaskStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed'

interface CrawlTaskState {
  status: CrawlTaskStatus
  taskId?: number
  progress?: {
    current: number
    total: number
    message?: string
  }
  error?: string
}

export default function StockAnalysisPage() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [debateResult, setDebateResult] = useState<DebateResponse | null>(null)
  const [klinePeriod, setKlinePeriod] = useState<KLinePeriod>('daily')
  const [crawlTask, setCrawlTask] = useState<CrawlTaskState>({ status: 'idle' })
  const [selectedNewsId, setSelectedNewsId] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const stockCode = code?.toUpperCase() || 'SH600519'
  const pureCode = extractCode(stockCode)

  // 获取当前周期配置
  const currentPeriodConfig = PERIOD_OPTIONS.find(p => p.value === klinePeriod) || PERIOD_OPTIONS[0]

  // 获取股票名称（从数据库查询）
  const { data: stockInfo } = useQuery({
    queryKey: ['stock', 'info', pureCode],
    queryFn: () => stockApi.searchRealtime(pureCode, 1),
    staleTime: 24 * 60 * 60 * 1000, // 缓存24小时
  })
  
  // 股票名称：优先使用查询结果，否则显示代码
  const stockName = stockInfo?.[0]?.name || stockCode

  // 获取股票概览
  const { data: overview, isLoading: overviewLoading, refetch: refetchOverview } = useQuery({
    queryKey: ['stock', 'overview', stockCode],
    queryFn: () => stockApi.getOverview(stockCode),
    staleTime: 5 * 60 * 1000,
  })

  // 获取关联新闻
  const { data: newsList, isLoading: newsLoading } = useQuery({
    queryKey: ['stock', 'news', stockCode],
    queryFn: () => stockApi.getNews(stockCode, { limit: 20 }),
    staleTime: 5 * 60 * 1000,
  })

  // 获取情感趋势
  const { data: sentimentTrend, isLoading: trendLoading } = useQuery({
    queryKey: ['stock', 'sentiment-trend', stockCode],
    queryFn: () => stockApi.getSentimentTrend(stockCode, 30),
    staleTime: 5 * 60 * 1000,
  })

  // 获取K线数据 - 支持多周期
  const { data: klineData, isLoading: klineLoading, refetch: refetchKline } = useQuery({
    queryKey: ['stock', 'kline', stockCode, klinePeriod, currentPeriodConfig.limit],
    queryFn: () => stockApi.getKLineData(stockCode, klinePeriod, currentPeriodConfig.limit),
    staleTime: klinePeriod === 'daily' ? 5 * 60 * 1000 : 60 * 1000, // 分钟级数据缓存1分钟
  })

  // 辩论 Mutation
  const debateMutation = useMutation({
    mutationFn: () => agentApi.runDebate({
      stock_code: stockCode,
      stock_name: stockName,
    }),
    onSuccess: (data) => {
      setDebateResult(data)
      if (data.success) {
        toast.success('辩论分析完成！')
      } else {
        toast.error(`辩论失败: ${data.error}`)
      }
    },
    onError: (error: Error) => {
      toast.error(`辩论失败: ${error.message}`)
    },
  })

  const handleStartDebate = () => {
    setDebateResult(null)
    debateMutation.mutate()
  }

  // 定向爬取任务状态查询
  const { data: crawlStatus, refetch: refetchCrawlStatus } = useQuery({
    queryKey: ['stock', 'targeted-crawl-status', stockCode],
    queryFn: () => stockApi.getTargetedCrawlStatus(stockCode),
    enabled: crawlTask.status === 'running' || crawlTask.status === 'pending',
    refetchInterval: crawlTask.status === 'running' ? 2000 : false, // 运行中时每2秒轮询
    staleTime: 0,
  })

  // 监听爬取状态变化
  useEffect(() => {
    // 只在有状态且当前任务正在进行时处理
    if (crawlStatus && (crawlTask.status === 'running' || crawlTask.status === 'pending')) {
      if (crawlStatus.status === 'completed') {
        setCrawlTask({ 
          status: 'completed', 
          taskId: crawlStatus.task_id,
          progress: { current: 100, total: 100, message: '爬取完成' }
        })
        // 强制刷新新闻列表（忽略缓存）
        queryClient.resetQueries({ queryKey: ['stock', 'news', stockCode] })
        queryClient.resetQueries({ queryKey: ['stock', 'overview', stockCode] })
        // 立即重新获取
        queryClient.refetchQueries({ queryKey: ['stock', 'news', stockCode], type: 'all' })
        queryClient.refetchQueries({ queryKey: ['stock', 'overview', stockCode], type: 'all' })
        toast.success(`定向爬取完成！新增 ${crawlStatus.saved_count || 0} 条新闻`)
      } else if (crawlStatus.status === 'failed') {
        setCrawlTask({ 
          status: 'failed', 
          taskId: crawlStatus.task_id,
          error: crawlStatus.error_message || '爬取失败'
        })
        toast.error(`定向爬取失败: ${crawlStatus.error_message || '未知错误'}`)
      } else if (crawlStatus.status === 'running') {
        // 更新进度和真实的 taskId
        setCrawlTask(prev => ({
          ...prev,
          status: 'running',
          taskId: crawlStatus.task_id || prev.taskId,
          progress: crawlStatus.progress || prev.progress
        }))
      }
    }
  }, [crawlStatus, crawlTask.status, stockCode, queryClient])

  // 页面加载时检查是否有进行中的任务
  useEffect(() => {
    const checkExistingTask = async () => {
      try {
        const status = await stockApi.getTargetedCrawlStatus(stockCode)
        // 只恢复正在运行或等待中的任务
        if (status && (status.status === 'running' || status.status === 'pending')) {
          setCrawlTask({
            status: status.status as CrawlTaskStatus,
            taskId: status.task_id,
            progress: status.progress
          })
        } else {
          // 其他状态（completed/failed/idle）重置为 idle
          setCrawlTask({ status: 'idle' })
        }
      } catch {
        // 没有进行中的任务，保持 idle 状态
        setCrawlTask({ status: 'idle' })
      }
    }
    checkExistingTask()
  }, [stockCode])

  // 定向爬取 Mutation
  const targetedCrawlMutation = useMutation({
    mutationFn: () => stockApi.startTargetedCrawl(stockCode, stockName),
    onSuccess: (data) => {
      if (data.success) {
        // 任务启动成功，设置为 running 状态
        // task_id 可能为空（因为 Celery 任务是异步创建的），使用临时标记
        setCrawlTask({ 
          status: 'running', 
          taskId: data.task_id || Date.now(),  // 使用 task_id 或临时 ID
          progress: { current: 0, total: 100, message: '开始爬取...' }
        })
        toast.success('定向爬取任务已启动')
        // 延迟开始轮询，等待后端创建任务记录
        setTimeout(() => refetchCrawlStatus(), 2000)
      } else {
        setCrawlTask({ status: 'failed', error: data.message })
        toast.error(`启动失败: ${data.message}`)
      }
    },
    onError: (error: Error) => {
      setCrawlTask({ status: 'failed', error: error.message })
      toast.error(`启动失败: ${error.message}`)
    },
  })

  const handleStartCrawl = () => {
    // 重置状态，清除之前的 taskId
    setCrawlTask({ status: 'pending', taskId: undefined })
    targetedCrawlMutation.mutate()
  }

  // 情感趋势指示器
  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up':
        return <TrendingUp className="w-5 h-5 text-emerald-500" />
      case 'down':
        return <TrendingDown className="w-5 h-5 text-rose-500" />
      default:
        return <Minus className="w-5 h-5 text-gray-500" />
    }
  }

  const getSentimentColor = (score: number | null) => {
    if (score === null) return 'gray'
    if (score > 0.1) return 'emerald'
    if (score < -0.1) return 'rose'
    return 'amber'
  }

  const getSentimentLabel = (score: number | null) => {
    if (score === null) return '未知'
    if (score > 0.3) return '强烈利好'
    if (score > 0.1) return '利好'
    if (score < -0.3) return '强烈利空'
    if (score < -0.1) return '利空'
    return '中性'
  }

  return (
    <div className="p-6 space-y-6 bg-gradient-to-br from-slate-50 to-blue-50 min-h-screen">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-6">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                {stockName}
              </h1>
              <Badge variant="outline" className="text-base px-3 py-1 bg-white">
                {stockCode}
              </Badge>
            </div>
            <p className="text-muted-foreground mt-1 flex items-center gap-2">
              <Activity className="w-4 h-4" />
              个股分析 · 智能体驱动的投资决策
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          {/* 返回按钮 */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/stock')}
            className="gap-2 hover:bg-gray-100"
          >
            <ArrowLeft className="w-4 h-4" />
            返回搜索
          </Button>
        </div>
      </div>

      {/* 概览卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-white/80 backdrop-blur-sm border-blue-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">关联新闻</p>
                <p className="text-2xl font-bold text-blue-600">
                  {overview?.total_news || 0}
                </p>
              </div>
              <Newspaper className="w-8 h-8 text-blue-500/50" />
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              已分析 {overview?.analyzed_news || 0} 条
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/80 backdrop-blur-sm border-emerald-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">整体情感</p>
                <p className={`text-2xl font-bold text-${getSentimentColor(overview?.avg_sentiment ?? null)}-600`}>
                  {overview?.avg_sentiment != null 
                    ? (overview.avg_sentiment > 0 ? '+' : '') + overview.avg_sentiment.toFixed(2)
                    : '--'}
                </p>
              </div>
              <BarChart3 className={`w-8 h-8 text-${getSentimentColor(overview?.avg_sentiment || null)}-500/50`} />
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              {getSentimentLabel(overview?.avg_sentiment || null)}
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/80 backdrop-blur-sm border-purple-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">近7天情感</p>
                <p className={`text-2xl font-bold text-${getSentimentColor(overview?.recent_sentiment ?? null)}-600`}>
                  {overview?.recent_sentiment != null
                    ? (overview.recent_sentiment > 0 ? '+' : '') + overview.recent_sentiment.toFixed(2)
                    : '--'}
                </p>
              </div>
              {getTrendIcon(overview?.sentiment_trend || 'stable')}
            </div>
            <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
              趋势：
              {overview?.sentiment_trend === 'up' && <span className="text-emerald-600">上升 ↑</span>}
              {overview?.sentiment_trend === 'down' && <span className="text-rose-600">下降 ↓</span>}
              {overview?.sentiment_trend === 'stable' && <span className="text-gray-600">稳定 →</span>}
            </p>
          </CardContent>
        </Card>

        <Card className="bg-white/80 backdrop-blur-sm border-orange-100">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">最新新闻</p>
                <p className="text-lg font-medium text-gray-700">
                  {overview?.last_news_time 
                    ? formatRelativeTime(overview.last_news_time)
                    : '暂无'}
                </p>
              </div>
              <Calendar className="w-8 h-8 text-orange-500/50" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* K线图 */}
      <Card className="bg-white/90">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-blue-500" />
                    K线图 · 真实行情
                  </CardTitle>
                  <CardDescription>
                    数据来源：akshare · 前复权 · 支持缩放拖拽
                  </CardDescription>
                </div>
                {klineData && klineData.length > 0 && (
                  <div className="flex items-center gap-4 text-sm">
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">收盘：</span>
                      <span className={`font-semibold ${
                        klineData[klineData.length - 1].change_percent !== undefined &&
                        klineData[klineData.length - 1].change_percent! >= 0
                          ? 'text-rose-600'
                          : 'text-emerald-600'
                      }`}>
                        ¥{klineData[klineData.length - 1].close.toFixed(2)}
                      </span>
                    </div>
                    {klineData[klineData.length - 1].change_percent !== undefined && (
                      <div className="flex items-center gap-1">
                        <span className="text-gray-500">涨跌：</span>
                        <Badge className={
                          klineData[klineData.length - 1].change_percent! >= 0
                            ? 'bg-rose-100 text-rose-700'
                            : 'bg-emerald-100 text-emerald-700'
                        }>
                          {klineData[klineData.length - 1].change_percent! >= 0 ? '+' : ''}
                          {klineData[klineData.length - 1].change_percent!.toFixed(2)}%
                        </Badge>
                      </div>
                    )}
                    {klineData[klineData.length - 1].turnover !== undefined && (
                      <div className="flex items-center gap-1">
                        <span className="text-gray-500">成交额：</span>
                        <span className="font-medium">
                          {(klineData[klineData.length - 1].turnover! / 100000000).toFixed(2)}亿
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
              {/* 周期选择器 */}
              <div className="flex items-center gap-1 mt-3 pt-3 border-t border-gray-100">
                <span className="text-sm text-gray-500 mr-2">周期：</span>
                {PERIOD_OPTIONS.map((option) => (
                  <Button
                    key={option.value}
                    variant={klinePeriod === option.value ? 'default' : 'ghost'}
                    size="sm"
                    onClick={() => setKlinePeriod(option.value)}
                    className={`h-7 px-3 text-xs ${
                      klinePeriod === option.value 
                        ? 'bg-blue-600 hover:bg-blue-700' 
                        : 'hover:bg-gray-100'
                    }`}
                  >
                    {option.label}
                  </Button>
                ))}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => refetchKline()}
                  disabled={klineLoading}
                  className="h-7 px-2 ml-2"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${klineLoading ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {klineLoading ? (
                <div className="h-[550px] flex items-center justify-center">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                </div>
              ) : klineData && klineData.length > 0 ? (
                <KLineChart
                  data={klineData}
                  height={550}
                  showVolume={true}
                  showMA={klinePeriod === 'daily'}
                  showMACD={false}
                  theme="light"
                />
              ) : (
                <div className="h-[550px] flex flex-col items-center justify-center text-gray-500">
                  <BarChart3 className="w-12 h-12 opacity-50 mb-3" />
                  <p>暂无K线数据</p>
                  <p className="text-sm mt-1">请检查股票代码是否正确</p>
                </div>
              )}
          </CardContent>
        </Card>

      {/* 关联新闻 */}
      <Card className="bg-white/90">
          <CardHeader>
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Newspaper className="w-5 h-5 text-blue-500" />
                  关联新闻
                </CardTitle>
                <CardDescription className="mt-1.5">
                  包含 {stockCode} 的相关财经新闻
                </CardDescription>
              </div>
              {/* 定向爬取按钮 */}
              <div className="flex items-center gap-2">
                {crawlTask.status === 'completed' && (
                  <span className="flex items-center gap-1 text-xs text-emerald-600">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    爬取完成
                  </span>
                )}
                {crawlTask.status === 'failed' && (
                  <span className="flex items-center gap-1 text-xs text-rose-600">
                    <AlertCircle className="w-3.5 h-3.5" />
                    爬取失败
                  </span>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleStartCrawl}
                  disabled={crawlTask.status === 'running' || crawlTask.status === 'pending' || targetedCrawlMutation.isPending}
                  className="gap-2"
                >
                  {crawlTask.status === 'running' || crawlTask.status === 'pending' ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>爬取中...</span>
                      {crawlTask.progress && (
                        <span className="text-xs text-gray-500">
                          {crawlTask.progress.message || `${crawlTask.progress.current}%`}
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      <Download className="w-4 h-4" />
                      定向爬取
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {newsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
              </div>
            ) : newsList && newsList.length > 0 ? (
              <div className="space-y-4">
                {newsList.map((news) => (
                  <div
                    key={news.id}
                    className="p-4 rounded-lg border border-gray-100 hover:border-blue-200 hover:bg-blue-50/30 transition-all cursor-pointer group"
                    onClick={() => {
                      setSelectedNewsId(news.id)
                      setDrawerOpen(true)
                    }}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <h3 className="font-medium text-gray-900 line-clamp-1 group-hover:text-blue-600 transition-colors">
                          {news.title}
                        </h3>
                        <p className="text-sm text-gray-500 line-clamp-2 mt-1">
                          {news.content}
                        </p>
                        <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                          <span>{news.source}</span>
                          <span>•</span>
                          <span>{news.publish_time ? formatRelativeTime(news.publish_time) : '时间未知'}</span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        {news.sentiment_score !== null && (
                          <Badge 
                            className={`
                              ${news.sentiment_score > 0.1 ? 'bg-emerald-100 text-emerald-700' : ''}
                              ${news.sentiment_score < -0.1 ? 'bg-rose-100 text-rose-700' : ''}
                              ${news.sentiment_score >= -0.1 && news.sentiment_score <= 0.1 ? 'bg-amber-100 text-amber-700' : ''}
                            `}
                          >
                            {news.sentiment_score > 0 ? '+' : ''}{news.sentiment_score.toFixed(2)}
                          </Badge>
                        )}
                        {news.has_analysis && (
                          <Badge variant="outline" className="text-xs">
                            已分析
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500">
                <Newspaper className="w-12 h-12 mx-auto opacity-50 mb-3" />
                <p>暂无关联新闻</p>
                <p className="text-sm mt-1">该股票还没有相关新闻数据</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 情感趋势图 */}
      <Card className="bg-white/90">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-purple-500" />
            新闻情感趋势
          </CardTitle>
          <CardDescription>
            近30天新闻情感分布与平均值
          </CardDescription>
        </CardHeader>
        <CardContent>
          {trendLoading ? (
            <div className="h-64 flex items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
            </div>
          ) : sentimentTrend && sentimentTrend.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={sentimentTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis 
                  dataKey="date" 
                  tick={{ fontSize: 10 }}
                  tickFormatter={(value) => value.slice(5)}
                />
                <YAxis 
                  yAxisId="left"
                  domain={[-1, 1]}
                  tick={{ fontSize: 10 }}
                />
                <YAxis 
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 10 }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(255, 255, 255, 0.95)',
                    borderRadius: '8px',
                    border: '1px solid #e5e7eb',
                  }}
                />
                <Legend />
                <Bar 
                  yAxisId="right"
                  dataKey="positive_count" 
                  stackId="a" 
                  fill="#10b981" 
                  name="利好"
                />
                <Bar 
                  yAxisId="right"
                  dataKey="neutral_count" 
                  stackId="a" 
                  fill="#f59e0b" 
                  name="中性"
                />
                <Bar 
                  yAxisId="right"
                  dataKey="negative_count" 
                  stackId="a" 
                  fill="#ef4444" 
                  name="利空"
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="avg_sentiment"
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  dot={false}
                  name="平均情感"
                />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-500">
              暂无数据
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bull vs Bear 辩论 */}
      <div className="space-y-6">
          {/* 触发辩论按钮 */}
          <Card className="bg-gradient-to-r from-emerald-50 to-rose-50 border-none">
            <CardContent className="py-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="flex -space-x-2">
                    <div className="w-12 h-12 rounded-full bg-emerald-500 flex items-center justify-center text-white shadow-lg">
                      <ThumbsUp className="w-6 h-6" />
                    </div>
                    <div className="w-12 h-12 rounded-full bg-rose-500 flex items-center justify-center text-white shadow-lg">
                      <ThumbsDown className="w-6 h-6" />
                    </div>
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">Bull vs Bear 智能体辩论</h3>
                    <p className="text-sm text-gray-500">
                      看多研究员 vs 看空研究员，投资经理综合裁决
                    </p>
                  </div>
                </div>
                <Button
                  onClick={handleStartDebate}
                  disabled={debateMutation.isPending}
                  className="bg-gradient-to-r from-emerald-500 to-rose-500 hover:from-emerald-600 hover:to-rose-600"
                >
                  {debateMutation.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      辩论中...
                    </>
                  ) : (
                    <>
                      <Swords className="w-4 h-4 mr-2" />
                      开始辩论
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* 辩论结果 */}
          {debateResult && debateResult.success && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* 看多观点 */}
              <Card className="bg-white/90 border-l-4 border-l-emerald-500">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-emerald-700">
                    <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center">
                      <ThumbsUp className="w-4 h-4 text-emerald-600" />
                    </div>
                    看多观点
                  </CardTitle>
                  <CardDescription>
                    <Bot className="w-3 h-3 inline mr-1" />
                    {debateResult.bull_analysis?.agent_name} · {debateResult.bull_analysis?.agent_role}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="prose prose-sm max-w-none prose-headings:text-emerald-800 prose-headings:font-semibold">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {debateResult.bull_analysis?.analysis || '分析生成中...'}
                    </ReactMarkdown>
                  </div>
                </CardContent>
              </Card>

              {/* 看空观点 */}
              <Card className="bg-white/90 border-l-4 border-l-rose-500">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-rose-700">
                    <div className="w-8 h-8 rounded-full bg-rose-100 flex items-center justify-center">
                      <ThumbsDown className="w-4 h-4 text-rose-600" />
                    </div>
                    看空观点
                  </CardTitle>
                  <CardDescription>
                    <Bot className="w-3 h-3 inline mr-1" />
                    {debateResult.bear_analysis?.agent_name} · {debateResult.bear_analysis?.agent_role}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="prose prose-sm max-w-none prose-headings:text-rose-800 prose-headings:font-semibold">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {debateResult.bear_analysis?.analysis || '分析生成中...'}
                    </ReactMarkdown>
                  </div>
                </CardContent>
              </Card>

              {/* 最终决策 */}
              <Card className="lg:col-span-2 bg-gradient-to-br from-blue-50 to-purple-50 border-blue-200">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-blue-800">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                      <Scale className="w-5 h-5 text-blue-600" />
                    </div>
                    投资经理决策
                    {debateResult.final_decision?.rating && (
                      <Badge 
                        className={`ml-2 ${
                          debateResult.final_decision.rating === '强烈推荐' || debateResult.final_decision.rating === '推荐'
                            ? 'bg-emerald-500'
                            : debateResult.final_decision.rating === '回避' || debateResult.final_decision.rating === '谨慎'
                            ? 'bg-rose-500'
                            : 'bg-amber-500'
                        }`}
                      >
                        {debateResult.final_decision.rating}
                      </Badge>
                    )}
                  </CardTitle>
                  <CardDescription className="flex items-center gap-4">
                    <span>
                      <Bot className="w-3 h-3 inline mr-1" />
                      {debateResult.final_decision?.agent_name} · {debateResult.final_decision?.agent_role}
                    </span>
                    {debateResult.execution_time && (
                      <span className="text-xs bg-blue-100 px-2 py-0.5 rounded">
                        耗时 {debateResult.execution_time.toFixed(1)}s
                      </span>
                    )}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="prose prose-sm max-w-none prose-headings:text-blue-800 prose-headings:font-semibold">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {debateResult.final_decision?.decision || '决策生成中...'}
                    </ReactMarkdown>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* 辩论失败 */}
          {debateResult && !debateResult.success && (
            <Card className="bg-rose-50 border-rose-200">
              <CardContent className="py-6">
                <p className="text-rose-700">辩论分析失败: {debateResult.error}</p>
              </CardContent>
            </Card>
          )}

          {/* 初始状态 */}
          {!debateResult && !debateMutation.isPending && (
            <Card className="bg-gray-50">
              <CardContent className="py-12 text-center text-gray-500">
                <Swords className="w-16 h-16 mx-auto opacity-50 mb-4" />
                <p className="text-lg">点击"开始辩论"启动智能体分析</p>
                <p className="text-sm mt-2">
                  系统将自动调用 Bull/Bear 研究员进行多角度分析，并由投资经理给出综合决策
                </p>
              </CardContent>
            </Card>
          )}
        </div>

      {/* 新闻详情抽屉 */}
      <NewsDetailDrawer
        newsId={selectedNewsId}
        open={drawerOpen}
        onOpenChange={(open) => {
          setDrawerOpen(open)
          if (!open) {
            // 延迟清除newsId，避免关闭动画时闪烁
            setTimeout(() => setSelectedNewsId(null), 300)
          }
        }}
      />
    </div>
  )
}
