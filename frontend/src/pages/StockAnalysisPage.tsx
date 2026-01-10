import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { stockApi, agentApi, knowledgeGraphApi, SSEDebateEvent } from '@/lib/api-client'
import { formatRelativeTime } from '@/lib/utils'
import NewsDetailDrawer from '@/components/NewsDetailDrawer'
import DebateChatRoom, { ChatMessage, ChatRole } from '@/components/DebateChatRoom'
import DebateHistorySidebar from '@/components/DebateHistorySidebar'
import { useDebateStore, DebateSession } from '@/store/useDebateStore'
import type { MentionTarget } from '@/components/MentionInput'
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
  ChevronDown,
  Copy,
  FileDown,
  Settings,
  Trash2,
  Network,
  Building2,
  StopCircle,
  History,
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
import { DebateModeSelector } from '@/components/DebateConfig'

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
  { value: 'daily', label: '日K', limit: 120 },  // 近3-4个月数据（扣除周末节假日约90个交易日）
  { value: '60m', label: '60分', limit: 200 },
  { value: '30m', label: '30分', limit: 200 },
  { value: '15m', label: '15分', limit: 200 },
  { value: '5m', label: '5分', limit: 300 },
  { value: '1m', label: '1分', limit: 400 },
]

// 复权类型配置
type KLineAdjust = 'qfq' | 'hfq' | ''
const ADJUST_OPTIONS: { value: KLineAdjust; label: string; tip: string }[] = [
  { value: 'qfq', label: '前复权', tip: '消除除权缺口，保持走势连续（推荐）' },
  { value: '', label: '不复权', tip: '显示真实交易价格，会有除权缺口' },
  { value: 'hfq', label: '后复权', tip: '以上市首日为基准，价格可能很高' },
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
  const [klineAdjust, setKlineAdjust] = useState<KLineAdjust>('qfq')  // 默认前复权，与国内主流软件一致
  const [crawlTask, setCrawlTask] = useState<CrawlTaskState>({ status: 'idle' })
  const [selectedNewsId, setSelectedNewsId] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [newsDisplayCount, setNewsDisplayCount] = useState(12) // 默认显示12条
  const [newsExpanded, setNewsExpanded] = useState(true) // 新闻是否展开
  const [debateMode, setDebateMode] = useState<string>('parallel') // 辩论模式
  const [showModelSelector, setShowModelSelector] = useState(false) // 模型选择器显示状态
  const [showKnowledgeGraph, setShowKnowledgeGraph] = useState(true) // 是否展示知识图谱
  
  // 流式辩论状态
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamPhase, setStreamPhase] = useState<string>('')
  const [streamingContent, setStreamingContent] = useState<{
    bull: string
    bear: string
    manager: string
    quick: string
  }>({ bull: '', bear: '', manager: '', quick: '' })
  const [activeAgent, setActiveAgent] = useState<string | null>(null)
  const [currentRound, setCurrentRound] = useState<{ round: number; maxRounds: number } | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const currentMessageIdRef = useRef<string | null>(null)
  const cancelStreamRef = useRef<(() => void) | null>(null)
  const chatMessagesRef = useRef<ChatMessage[]>([])
  
  // 保持 ref 同步
  useEffect(() => {
    chatMessagesRef.current = chatMessages
  }, [chatMessages])
  
  const stockCode = code?.toUpperCase() || 'SH600519'
  const pureCode = extractCode(stockCode)
  
  // 辩论历史 Store
  const { 
    currentSession,
    startSession, 
    addMessage: addMessageToStore, 
    syncMessages,
    getStockSessions,
    loadSession,
    clearStockHistory,
    syncToBackend,
    loadFromBackend,
    saveAnalysisResult,
    updateSessionStatus,
    deleteSession,
    getLatestInProgressSession
  } = useDebateStore()
  
  // 历史侧边栏状态
  const [showHistorySidebar, setShowHistorySidebar] = useState(false)
  
  // 获取该股票的历史会话（直接从 Store 订阅，确保数据变化时自动更新）
  const allSessions = useDebateStore(state => state.sessions)
  const historySessions = useMemo(() => allSessions[stockCode] || [], [stockCode, allSessions])
  
  // 页面加载时从后端加载历史
  useEffect(() => {
    loadFromBackend(stockCode)
  }, [stockCode, loadFromBackend])

  // 页面加载时检查是否有未完成的会话，并提示恢复
  useEffect(() => {
    const checkAndRestoreSession = () => {
      const inProgressSession = getLatestInProgressSession(stockCode)
      if (inProgressSession && inProgressSession.messages.length > 0) {
        // 有未完成的会话，提示用户恢复
        const shouldRestore = window.confirm(
          `检测到有未完成的${inProgressSession.mode === 'realtime_debate' ? '实时辩论' : '分析'}会话（${inProgressSession.messages.length} 条消息），是否恢复？`
        )
        if (shouldRestore) {
          restoreSessionState(inProgressSession)
          toast.success('已恢复上次会话')
        } else {
          // 标记为中断
          updateSessionStatus('interrupted')
        }
      } else if (inProgressSession && inProgressSession.analysisResult) {
        // 有分析结果的会话，直接恢复
        restoreSessionState(inProgressSession)
      }
    }
    
    // 延迟执行，确保 store 数据已加载
    const timer = setTimeout(checkAndRestoreSession, 500)
    return () => clearTimeout(timer)
  }, [stockCode])

  // 恢复会话状态到页面
  const restoreSessionState = useCallback((session: DebateSession) => {
    // 恢复模式
    setDebateMode(session.mode)
    
    // 恢复聊天消息（需要类型转换）
    if (session.messages.length > 0) {
      const restoredMessages: ChatMessage[] = session.messages.map(m => ({
        id: m.id,
        role: m.role as ChatRole,
        content: m.content,
        timestamp: new Date(m.timestamp),
        round: m.round,
        isStreaming: false
      }))
      setChatMessages(restoredMessages)
    }
    
    // 恢复分析结果（并行/快速模式）
    if (session.analysisResult) {
      setStreamingContent({
        bull: session.analysisResult.bull || '',
        bear: session.analysisResult.bear || '',
        manager: session.analysisResult.manager || '',
        quick: session.analysisResult.quick || ''
      })
      
      // 如果有最终决策，设置 debateResult
      if (session.analysisResult.finalDecision || session.analysisResult.bull || session.analysisResult.bear) {
        setDebateResult({
          success: true,
          stock_code: session.stockCode,
          stock_name: session.stockName,
          mode: session.mode as 'parallel' | 'realtime_debate' | 'quick_analysis',
          bull_analysis: session.analysisResult.bull ? {
            success: true,
            agent_name: 'BullResearcher',
            stance: 'bull',
            analysis: session.analysisResult.bull
          } : undefined,
          bear_analysis: session.analysisResult.bear ? {
            success: true,
            agent_name: 'BearResearcher',
            stance: 'bear',
            analysis: session.analysisResult.bear
          } : undefined,
          final_decision: session.analysisResult.finalDecision ? {
            success: true,
            agent_name: 'InvestmentManager',
            rating: session.analysisResult.finalDecision.rating,
            decision: session.analysisResult.finalDecision.decision
          } : undefined,
          quick_analysis: session.analysisResult.quick ? {
            success: true,
            analysis: session.analysisResult.quick
          } : undefined,
          execution_time: session.analysisResult.executionTime
        })
      }
    }
    
    // 加载会话到 store
    loadSession(session.stockCode, session.id)
  }, [loadSession])

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
    queryFn: () => stockApi.getNews(stockCode, { limit: 200 }), // 获取更多数据，前端分页
    staleTime: 5 * 60 * 1000,
  })

  // 计算排序后的展示新闻（按时间从新到旧）
  const displayedNews = useMemo(() => {
    if (!newsList) return []
    const sorted = [...newsList].sort((a, b) => {
      const timeA = a.publish_time ? new Date(a.publish_time).getTime() : 0
      const timeB = b.publish_time ? new Date(b.publish_time).getTime() : 0
      return timeB - timeA // 降序排列（最新的在前）
    })
    return sorted.slice(0, newsDisplayCount)
  }, [newsList, newsDisplayCount])

  // 是否还有更多新闻
  const hasMoreNews = (newsList?.length || 0) > newsDisplayCount
  
  // 是否有历史新闻数据
  const hasHistoryNews = newsList && newsList.length > 0

  // 获取新闻卡片样式（根据情感分数）
  const getNewsCardStyle = (sentiment: number | null) => {
    const baseStyle = "flex flex-col transition-all duration-300 border min-w-0 h-full hover:shadow-lg hover:-translate-y-1 cursor-pointer"
    
    if (sentiment === null) {
      return `${baseStyle} bg-white border-gray-200 hover:border-blue-300`
    }

    if (sentiment > 0.1) {
      // 利好：绿色渐变
      return `${baseStyle} bg-gradient-to-br from-emerald-50 to-white border-emerald-200 hover:border-emerald-400 hover:shadow-emerald-200/60`
    }
    
    if (sentiment < -0.1) {
      // 利空：红色渐变
      return `${baseStyle} bg-gradient-to-br from-rose-50 to-white border-rose-200 hover:border-rose-400 hover:shadow-rose-200/60`
    }

    // 中性：蓝灰色渐变
    return `${baseStyle} bg-gradient-to-br from-slate-50 to-white border-slate-200 hover:border-slate-400 hover:shadow-slate-200/60`
  }

  // 获取情感趋势
  const { data: sentimentTrend, isLoading: trendLoading } = useQuery({
    queryKey: ['stock', 'sentiment-trend', stockCode],
    queryFn: () => stockApi.getSentimentTrend(stockCode, 30),
    staleTime: 5 * 60 * 1000,
  })

  // 获取知识图谱
  const { data: knowledgeGraph, isLoading: kgLoading, refetch: refetchKG } = useQuery({
    queryKey: ['knowledge-graph', stockCode],
    queryFn: () => knowledgeGraphApi.getCompanyGraph(stockCode),
    staleTime: 10 * 60 * 1000, // 缓存10分钟
  })

  // 获取K线数据 - 支持多周期和复权类型
  const { data: klineData, isLoading: klineLoading, refetch: refetchKline } = useQuery({
    queryKey: ['stock', 'kline', stockCode, klinePeriod, currentPeriodConfig.limit, klineAdjust],
    queryFn: async () => {
      const actualAdjust = klinePeriod === 'daily' ? klineAdjust : ''
      console.log(`🔍 Fetching kline data: code=${stockCode}, period=${klinePeriod}, limit=${currentPeriodConfig.limit}, adjust=${actualAdjust}`)
      
      const data = await stockApi.getKLineData(
        stockCode, 
        klinePeriod, 
        currentPeriodConfig.limit,
        actualAdjust
      )
      
      if (data && data.length > 0) {
        console.log(`✅ Received ${data.length} kline data points, latest: ${data[data.length - 1].date}, close: ${data[data.length - 1].close}`)
      } else {
        console.warn(`⚠️ Received empty kline data`)
      }
      
      return data
    },
    staleTime: 0, // 禁用缓存，每次都重新获取以避免混乱
    gcTime: 0, // 立即丢弃缓存 (React Query v5: cacheTime改名为gcTime)
  })

  // 辩论 Mutation（非流式备用）
  const debateMutation = useMutation({
    mutationFn: (mode: string) => agentApi.runDebate({
      stock_code: stockCode,
      stock_name: stockName,
      mode: mode as 'parallel' | 'realtime_debate' | 'quick_analysis',
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

  // Agent 名称到聊天角色的映射
  const agentToRole = useCallback((agent: string): ChatRole => {
    switch (agent) {
      case 'BullResearcher': return 'bull'
      case 'BearResearcher': return 'bear'
      case 'InvestmentManager': return 'manager'
      case 'DataCollector': return 'data_collector'
      case 'QuickAnalyst': return 'manager' // 快速分析师用经理角色
      default: return 'system'
    }
  }, [])

  // 处理 SSE 事件
  const handleSSEEvent = useCallback((event: SSEDebateEvent) => {
    console.log('SSE Event:', event.type, event.data)
    
    switch (event.type) {
      case 'task_plan':
        // 搜索计划事件
        const plan = event.data as any
        setChatMessages(prev => {
          // 查找最后一条消息，如果是数据专员的思考中消息，则替换
          const lastMsg = prev[prev.length - 1]
          if (lastMsg && lastMsg.role === 'data_collector' && !lastMsg.content) {
            return prev.map(msg => 
              msg.id === lastMsg.id 
                ? { ...msg, searchPlan: plan, searchStatus: 'pending' } 
                : msg
            )
          }
          // 否则添加新消息
          return [...prev, {
            id: `plan-${Date.now()}`,
            role: 'data_collector' as ChatRole,
            content: '',
            timestamp: new Date(),
            searchPlan: plan,
            searchStatus: 'pending'
          }]
        })
        break

      case 'phase':
        setStreamPhase(event.data.phase || '')
        // 更新轮次信息
        if (event.data.round && event.data.max_rounds) {
          setCurrentRound({ round: event.data.round, maxRounds: event.data.max_rounds })
          
          // 实时辩论模式：添加轮次系统消息
          if (debateMode === 'realtime_debate') {
            setChatMessages(prev => [...prev, {
              id: `system-round-${event.data.round}`,
              role: 'system' as ChatRole,
              content: `📢 第 ${event.data.round}/${event.data.max_rounds} 轮辩论开始`,
              timestamp: new Date()
            }])
          }
        }
        if (event.data.phase === 'complete') {
          toast.success('辩论分析完成！')
          // 添加完成消息
          if (debateMode === 'realtime_debate') {
            setChatMessages(prev => [...prev, {
              id: 'system-complete',
              role: 'system' as ChatRole,
              content: '✅ 辩论结束，投资经理已做出最终决策',
              timestamp: new Date()
            }])
          }
        }
        if (event.data.phase === 'data_collection' && debateMode === 'realtime_debate') {
          setChatMessages(prev => [...prev, {
            id: 'system-start',
            role: 'system' as ChatRole,
            content: '🎬 辩论开始，数据专员正在准备资料...',
            timestamp: new Date()
          }])
        }
        break
        
      case 'agent':
        const { agent, content, is_start, is_end, is_chunk, round } = event.data
        const chatRole = agentToRole(agent || '')
        
        if (is_start) {
          setActiveAgent(agent || null)
          
          // 实时辩论模式：创建新消息
          if (debateMode === 'realtime_debate') {
            const newMsgId = `msg-${Date.now()}-${agent}`
            currentMessageIdRef.current = newMsgId
            setChatMessages(prev => [...prev, {
              id: newMsgId,
              role: chatRole,
              content: '',
              timestamp: new Date(),
              round: round,
              isStreaming: true
            }])
          }
          
          // 旧逻辑：分栏模式的轮次标记
          if (round && debateMode !== 'realtime_debate') {
            setStreamingContent(prev => {
              const key = agent === 'BullResearcher' ? 'bull' 
                        : agent === 'BearResearcher' ? 'bear'
                        : null
              if (key && round > 1) {
                return { ...prev, [key]: prev[key as keyof typeof prev] + `\n\n---\n**【第${round}轮】**\n` }
              }
              return prev
            })
          }
        } else if (is_end) {
          setActiveAgent(null)
          
          // 实时辩论模式：标记消息完成
          if (debateMode === 'realtime_debate' && currentMessageIdRef.current) {
            setChatMessages(prev => prev.map(msg => 
              msg.id === currentMessageIdRef.current 
                ? { ...msg, isStreaming: false }
                : msg
            ))
            currentMessageIdRef.current = null
          }
        } else if (is_chunk && content) {
          // 实时辩论模式：追加到当前消息
          if (debateMode === 'realtime_debate' && currentMessageIdRef.current) {
            setChatMessages(prev => prev.map(msg => 
              msg.id === currentMessageIdRef.current 
                ? { ...msg, content: msg.content + content }
                : msg
            ))
          }
          
          // 旧逻辑：分栏模式
          setStreamingContent(prev => {
            const key = agent === 'BullResearcher' ? 'bull' 
                      : agent === 'BearResearcher' ? 'bear'
                      : agent === 'InvestmentManager' ? 'manager'
                      : agent === 'QuickAnalyst' ? 'quick'
                      : null
            if (key) {
              return { ...prev, [key]: prev[key as keyof typeof prev] + content }
            }
            return prev
          })
        }
        
        // 处理 DataCollector 的非流式消息
        if (agent === 'DataCollector' && content && !is_chunk && debateMode === 'realtime_debate') {
          setChatMessages(prev => [...prev, {
            id: `data-collector-${Date.now()}`,
            role: 'data_collector' as ChatRole,
            content: content,
            timestamp: new Date()
          }])
        }
        break
        
      case 'result':
        // 最终结果
        setDebateResult({
          success: event.data.success || false,
          stock_code: stockCode,
          stock_name: stockName,
          mode: event.data.mode as any,
          bull_analysis: event.data.bull_analysis,
          bear_analysis: event.data.bear_analysis,
          final_decision: event.data.final_decision,
          quick_analysis: event.data.quick_analysis,
          debate_id: event.data.debate_id,
          execution_time: event.data.execution_time
        })
        setIsStreaming(false)
        setCurrentRound(null)
        
        // 保存分析结果到 store（用于历史恢复）
        saveAnalysisResult({
          bull: event.data.bull_analysis?.analysis,
          bear: event.data.bear_analysis?.analysis,
          manager: event.data.final_decision?.decision,
          quick: event.data.quick_analysis?.analysis,
          finalDecision: event.data.final_decision ? {
            rating: event.data.final_decision.rating,
            decision: event.data.final_decision.decision
          } : undefined,
          executionTime: event.data.execution_time
        })
        break
        
      case 'error':
        toast.error(`辩论失败: ${event.data.message}`)
        setIsStreaming(false)
        setCurrentRound(null)
        // 添加错误消息
        if (debateMode === 'realtime_debate') {
          setChatMessages(prev => [...prev, {
            id: 'system-error',
            role: 'system' as ChatRole,
            content: `❌ 发生错误: ${event.data.message}`,
            timestamp: new Date()
          }])
        }
        break
    }
  }, [stockCode, stockName, debateMode, agentToRole])

  // 处理追问 SSE 事件
  const handleFollowUpEvent = useCallback((event: SSEDebateEvent) => {
    console.log('FollowUp Event:', event.type, event.data)
    
    switch (event.type) {
      case 'task_plan':
        const plan = event.data as any
        setChatMessages(prev => [...prev, {
          id: `plan-${Date.now()}`,
          role: 'data_collector' as ChatRole,
          content: '',
          timestamp: new Date(),
          searchPlan: plan,
          searchStatus: 'pending'
        }])
        setIsStreaming(false) // 计划生成完就不再流式了，等待确认
        break

      case 'agent':
        const { agent, content, is_start, is_end, is_chunk } = event.data
        const chatRole = agentToRole(agent || '')
        
        if (is_start) {
          setActiveAgent(agent || null)
          // 创建新消息
          const newMsgId = `followup-${Date.now()}-${agent}`
          currentMessageIdRef.current = newMsgId
          setChatMessages(prev => [...prev, {
            id: newMsgId,
            role: chatRole,
            content: '',
            timestamp: new Date(),
            isStreaming: true
          }])
        } else if (is_end) {
          setActiveAgent(null)
          // 标记消息完成
          if (currentMessageIdRef.current) {
            setChatMessages(prev => prev.map(msg => 
              msg.id === currentMessageIdRef.current 
                ? { ...msg, isStreaming: false }
                : msg
            ))
            currentMessageIdRef.current = null
          }
          setIsStreaming(false)
        } else if (is_chunk && content) {
          // 追加到当前消息
          if (currentMessageIdRef.current) {
            setChatMessages(prev => prev.map(msg => 
              msg.id === currentMessageIdRef.current 
                ? { ...msg, content: msg.content + content }
                : msg
            ))
          }
        }
        break
        
      case 'complete':
        setIsStreaming(false)
        break
        
      case 'error':
        toast.error(`回复失败: ${event.data.message}`)
        setIsStreaming(false)
        break
    }
  }, [agentToRole])

  // 处理用户发送消息（支持 @ 提及）
  const handleUserSendMessage = useCallback((content: string, mentions?: MentionTarget[]) => {
    // 添加用户消息到聊天
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user' as ChatRole,
      content: content,
      timestamp: new Date()
    }
    setChatMessages(prev => [...prev, userMessage])
    
    // 同步到 Store
    if (currentSession) {
      addMessageToStore(userMessage)
    }
    
    // 角色名称映射
    const roleNames: Record<string, string> = {
      bull: '多方辩手',
      bear: '空方辩手', 
      manager: '投资经理',
      data_collector: '数据专员',
      user: '用户',
      system: '系统'
    }
    
    // 构建上下文（从之前的聊天记录中提取）
    const contextSummary = chatMessages
      .filter(m => m.role !== 'system' && m.role !== 'user')
      .slice(-6) // 最近6条消息
      .map(m => `【${roleNames[m.role] || m.role}】${m.content.slice(0, 200)}`)
      .join('\n')
    
    // 开始流式请求
    setIsStreaming(true)
    
    const cancel = agentApi.followUp(
      {
        stock_code: stockCode,
        stock_name: stockName,
        question: content,
        context: contextSummary
      },
      handleFollowUpEvent,
      (error) => {
        toast.error(`回复失败: ${error.message}`)
        setIsStreaming(false)
      },
      () => {
        setIsStreaming(false)
      }
    )
    
    // 保存取消函数
    cancelStreamRef.current = cancel
  }, [stockCode, stockName, chatMessages, handleFollowUpEvent])

  // 处理确认搜索
  const handleConfirmSearch = useCallback((plan: any, msgId: string) => {
    // 更新消息状态为执行中
    setChatMessages(prev => prev.map(msg => 
      msg.id === msgId ? { ...msg, searchStatus: 'executing' } : msg
    ))
    
    setIsStreaming(true)
    
    // 执行搜索
    agentApi.executeSearch(
      plan,
      (event) => {
        if (event.type === 'agent') {
          // 搜索结果返回
          const { content } = event.data
          setChatMessages(prev => prev.map(msg => 
            msg.id === msgId 
              ? { ...msg, content: content || '', searchStatus: 'completed' } 
              : msg
          ))
          
          // 同步到 Store
          if (currentSession) {
            const updatedMsg = chatMessages.find(m => m.id === msgId)
            if (updatedMsg) {
              addMessageToStore({ ...updatedMsg, content: content || '', searchStatus: 'completed' })
            }
          }
        }
      },
      (error) => {
        toast.error(`搜索执行失败: ${error.message}`)
        setIsStreaming(false)
        setChatMessages(prev => prev.map(msg => 
          msg.id === msgId ? { ...msg, searchStatus: 'pending' } : msg
        ))
      },
      () => {
        setIsStreaming(false)
        // 先同步消息到 Store，再保存到后端
        syncMessages(chatMessagesRef.current)
        syncToBackend(stockCode)
      }
    )
  }, [stockCode, currentSession, chatMessages, addMessageToStore, syncMessages, syncToBackend])

  // 处理取消搜索
  const handleCancelSearch = useCallback((msgId: string) => {
    setChatMessages(prev => prev.map(msg => 
      msg.id === msgId ? { ...msg, searchStatus: 'cancelled' } : msg
    ))
    toast.info('已取消搜索任务')
  }, [])

  const handleStartDebate = useCallback(() => {
    // 重置状态
    setDebateResult(null)
    setStreamingContent({ bull: '', bear: '', manager: '', quick: '' })
    setStreamPhase('')
    setActiveAgent(null)
    setCurrentRound(null)
    setChatMessages([]) // 重置聊天消息
    currentMessageIdRef.current = null
    setIsStreaming(true)
    
    // 创建新的辩论会话
    startSession(stockCode, stockName, debateMode)
    
    // 取消之前的流
    if (cancelStreamRef.current) {
      cancelStreamRef.current()
    }
    
    // 开始新的流式辩论
    const cancel = agentApi.runDebateStream(
      {
        stock_code: stockCode,
        stock_name: stockName,
        mode: debateMode as 'parallel' | 'realtime_debate' | 'quick_analysis',
      },
      handleSSEEvent,
      (error) => {
        toast.error(`辩论失败: ${error.message}`)
        setIsStreaming(false)
        updateSessionStatus('interrupted')
      },
      () => {
        // 完成后保存分析结果并同步到后端
        console.log('🏁 Debate completed!')
        console.log('🏁 chatMessagesRef.current:', chatMessagesRef.current.length, 'messages')
        console.log('🏁 Message roles:', chatMessagesRef.current.map(m => m.role))
        
        setIsStreaming(false)
        updateSessionStatus('completed')
        // 使用 ref 获取最新的消息列表，批量同步到 Store
        syncMessages(chatMessagesRef.current)
        // 然后同步到后端
        syncToBackend(stockCode)
      }
    )
    
    cancelStreamRef.current = cancel
  }, [stockCode, stockName, debateMode, handleSSEEvent, startSession, syncMessages, syncToBackend])
  
  // 组件卸载时取消流
  useEffect(() => {
    return () => {
      if (cancelStreamRef.current) {
        cancelStreamRef.current()
      }
    }
  }, [])

  // 定期保存流式内容到 store（防止刷新丢失）
  useEffect(() => {
    if (!isStreaming) return
    
    const saveInterval = setInterval(() => {
      // 保存当前分析内容（并行/快速模式）
      if (streamingContent.bull || streamingContent.bear || streamingContent.manager || streamingContent.quick) {
        saveAnalysisResult({
          bull: streamingContent.bull || undefined,
          bear: streamingContent.bear || undefined,
          manager: streamingContent.manager || undefined,
          quick: streamingContent.quick || undefined
        })
      }
    }, 3000) // 每3秒保存一次
    
    return () => clearInterval(saveInterval)
  }, [isStreaming, streamingContent, saveAnalysisResult])

  // 实时辩论模式：同步所有完成的消息到 store
  useEffect(() => {
    if (debateMode !== 'realtime_debate' || chatMessages.length === 0 || !currentSession) return
    
    // 找出所有已完成但尚未在 Store 中的消息
    const storeMessageIds = new Set(currentSession.messages.map(m => m.id))
    const completedMessages = chatMessages.filter(m => 
      !m.isStreaming && // 已完成
      (m.content || m.searchPlan) && // 有内容
      !storeMessageIds.has(m.id) // 不在 Store 中
    )
    
    // 逐个添加到 Store
    for (const msg of completedMessages) {
      addMessageToStore(msg)
    }
  }, [chatMessages, debateMode, currentSession, addMessageToStore])

  // 定向爬取任务状态查询
  const { data: crawlStatus, refetch: refetchCrawlStatus } = useQuery({
    queryKey: ['stock', 'targeted-crawl-status', stockCode],
    queryFn: () => stockApi.getTargetedCrawlStatus(stockCode),
    enabled: crawlTask.status === 'running' || crawlTask.status === 'pending',
    refetchInterval: (crawlTask.status === 'running' || crawlTask.status === 'pending') ? 2000 : false, // pending/running 时每2秒轮询
    staleTime: 0,
  })

  // 监听爬取状态变化
  useEffect(() => {
    // 只在有状态且当前任务正在进行时处理
    if (crawlStatus && (crawlTask.status === 'running' || crawlTask.status === 'pending')) {
      // 重要：检查 task_id 是否匹配，避免使用旧任务的状态
      const isMatchingTask = !crawlTask.taskId || !crawlStatus.task_id || crawlTask.taskId === crawlStatus.task_id
      
      if (!isMatchingTask) {
        console.warn('Task ID mismatch, ignoring status update', { 
          currentTaskId: crawlTask.taskId, 
          statusTaskId: crawlStatus.task_id 
        })
        return
      }
      
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
      } else if (crawlStatus.status === 'running' || crawlStatus.status === 'pending') {
        // 更新进度和真实的 taskId
        setCrawlTask(prev => ({
          ...prev,
          status: crawlStatus.status as CrawlTaskStatus,
          taskId: crawlStatus.task_id || prev.taskId,
          progress: crawlStatus.progress || prev.progress
        }))
      }
    }
  }, [crawlStatus, crawlTask.status, crawlTask.taskId, stockCode, queryClient])

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
        // 任务启动成功，设置为 pending 状态（后端已创建任务记录）
        setCrawlTask({ 
          status: 'pending', 
          taskId: data.task_id!,  // 现在 task_id 一定存在
          progress: { current: 0, total: 100, message: '任务已创建，等待执行...' }
        })
        toast.success('定向爬取任务已启动')
        // 立即开始轮询（不需要延迟，因为任务记录已创建）
        refetchCrawlStatus()
      } else if (data.task_id) {
        // 已有正在进行的任务，恢复到该任务的状态
        setCrawlTask({ 
          status: 'running', 
          taskId: data.task_id,
          progress: { current: 0, total: 100, message: '正在爬取中...' }
        })
        toast.info('该股票已有正在进行的爬取任务，正在同步状态...')
        // 立即获取任务状态
        refetchCrawlStatus()
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

  const handleStopCrawl = async () => {
    if (window.confirm('确定要停止当前的爬取任务吗？')) {
      try {
        // 调用后端 API 取消任务
        const result = await stockApi.cancelTargetedCrawl(stockCode)
        if (result.success) {
          setCrawlTask({ status: 'idle' })
          toast.info(result.message || '已停止爬取任务')
        } else {
          toast.error(result.message || '停止任务失败')
        }
      } catch (error: any) {
        console.error('Failed to cancel crawl task:', error)
        // 即使后端失败，也重置前端状态
      setCrawlTask({ status: 'idle' })
      toast.info('已停止爬取任务')
      }
    }
  }

  // 清除新闻 Mutation
  const clearNewsMutation = useMutation({
    mutationFn: () => stockApi.clearStockNews(stockCode),
    onSuccess: (data) => {
      if (data.success) {
        toast.success(`已清除 ${data.deleted_count || 0} 条新闻`)
        // 强制刷新新闻列表
        queryClient.resetQueries({ queryKey: ['stock', 'news', stockCode] })
        queryClient.resetQueries({ queryKey: ['stock', 'overview', stockCode] })
        queryClient.refetchQueries({ queryKey: ['stock', 'news', stockCode], type: 'all' })
        queryClient.refetchQueries({ queryKey: ['stock', 'overview', stockCode], type: 'all' })
      } else {
        toast.error(`清除失败: ${data.message}`)
      }
    },
    onError: (error: Error) => {
      toast.error(`清除失败: ${error.message}`)
    },
  })

  const handleClearNews = () => {
    if (window.confirm(`确定要清除「${stockName}」的所有新闻吗？此操作不可恢复！`)) {
      clearNewsMutation.mutate()
    }
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

  // 复制内容到剪贴板
  const handleCopyContent = (content: string, label: string) => {
    navigator.clipboard.writeText(content).then(() => {
      toast.success(`${label}已复制到剪贴板`)
    }).catch(() => {
      toast.error('复制失败')
    })
  }

  // 导出内容到本地文件
  const handleExportToFile = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    toast.success('文件已导出')
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
          {/* 历史记录按钮 */}
          {historySessions.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowHistorySidebar(true)}
              className="gap-2 hover:bg-indigo-50 border-indigo-200 text-indigo-600"
            >
              <History className="w-4 h-4" />
              历史 ({historySessions.length})
            </Button>
          )}
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

      {/* 知识图谱卡片 */}
      {showKnowledgeGraph && knowledgeGraph && knowledgeGraph.graph_exists && (
        <Card className="bg-gradient-to-r from-purple-50 to-blue-50 border-purple-200">
          <CardHeader>
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-purple-800">
                  <Network className="w-5 h-5 text-purple-600" />
                  知识图谱 · 智能检索
                </CardTitle>
                <CardDescription className="mt-1.5">
                  基于多维度关键词并发检索，提升召回率
                </CardDescription>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => refetchKG()}
                className="h-8 px-2"
                title="刷新图谱"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${kgLoading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 名称变体 */}
            {knowledgeGraph.name_variants && knowledgeGraph.name_variants.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">名称变体</p>
                <div className="flex flex-wrap gap-1">
                  {knowledgeGraph.name_variants.map((variant, idx) => (
                    <Badge key={idx} variant="outline" className="text-xs bg-white">
                      {variant}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            
            {/* 业务线 */}
            {knowledgeGraph.businesses && knowledgeGraph.businesses.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">主营业务</p>
                <div className="flex flex-wrap gap-1">
                  {knowledgeGraph.businesses
                    .filter(b => b.status === 'active')
                    .slice(0, 5)
                    .map((business, idx) => (
                      <Badge 
                        key={idx} 
                        className={`text-xs ${
                          business.type === 'new' 
                            ? 'bg-emerald-100 text-emerald-700' 
                            : 'bg-blue-100 text-blue-700'
                        }`}
                        title={business.description || business.name}
                      >
                        {business.type === 'new' && '🆕 '}
                        {business.name}
                      </Badge>
                    ))}
                </div>
              </div>
            )}
            
            {/* 关联概念 */}
            {knowledgeGraph.concepts && knowledgeGraph.concepts.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">关联概念</p>
                <div className="flex flex-wrap gap-1">
                  {knowledgeGraph.concepts.slice(0, 6).map((concept, idx) => (
                    <Badge key={idx} className="text-xs bg-purple-100 text-purple-700">
                      {concept}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            
            {/* 检索策略 */}
            {knowledgeGraph.search_queries && knowledgeGraph.search_queries.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">并发检索查询（{knowledgeGraph.search_queries.length}条）</p>
                <div className="text-xs text-gray-600 bg-white rounded p-2 max-h-20 overflow-y-auto">
                  {knowledgeGraph.search_queries.slice(0, 3).map((query, idx) => (
                    <div key={idx} className="truncate">• {query}</div>
                  ))}
                  {knowledgeGraph.search_queries.length > 3 && (
                    <div className="text-gray-400">... 还有 {knowledgeGraph.search_queries.length - 3} 条</div>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

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
                    数据来源：akshare · {ADJUST_OPTIONS.find(o => o.value === klineAdjust)?.label || '前复权'} · 支持缩放拖拽
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
              {/* 周期和复权选择器 */}
              <div className="flex items-center gap-1 mt-3 pt-3 border-t border-gray-100 flex-wrap">
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
                
                {/* 复权类型选择器（仅日线有效） */}
                {klinePeriod === 'daily' && (
                  <>
                    <span className="text-gray-300 mx-2">|</span>
                    <span className="text-sm text-gray-500 mr-2" title="前复权可消除分红送股产生的缺口，保持K线连续性">
                      复权：
                    </span>
                    {ADJUST_OPTIONS.map((option) => (
                      <Button
                        key={option.value}
                        variant={klineAdjust === option.value ? 'default' : 'ghost'}
                        size="sm"
                        onClick={() => setKlineAdjust(option.value)}
                        title={option.tip}
                        className={`h-7 px-3 text-xs ${
                          klineAdjust === option.value 
                            ? 'bg-amber-600 hover:bg-amber-700' 
                            : 'hover:bg-gray-100'
                        }`}
                      >
                        {option.label}
                        {option.value === 'qfq' && <span className="ml-1 text-[10px] opacity-70">推荐</span>}
                      </Button>
                    ))}
                  </>
                )}
                
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
                  period={klinePeriod}
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
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Newspaper className="w-5 h-5 text-blue-500" />
                      关联新闻
                    </CardTitle>
                    <CardDescription className="mt-1.5">
                      包含 {stockCode} 的相关财经新闻 {newsList && `（共${newsList.length}条）`}
                    </CardDescription>
                  </div>
                  {/* 展开/折叠按钮 */}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setNewsExpanded(!newsExpanded)
                      if (newsExpanded) {
                        // 折叠时重置为12条
                        setNewsDisplayCount(12)
                      }
                    }}
                    className="gap-2"
                  >
                    <ChevronDown className={`w-4 h-4 transition-transform ${newsExpanded ? '' : 'rotate-180'}`} />
                    {newsExpanded ? '折叠' : '展开'}
                  </Button>
                </div>
              </div>
              {/* 定向爬取按钮组 */}
              <div className="flex items-center gap-2">
                {/* 一键清除按钮 - 仅在有新闻时显示 */}
                {hasHistoryNews && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleClearNews}
                    disabled={clearNewsMutation.isPending || crawlTask.status === 'running' || crawlTask.status === 'pending'}
                    className="gap-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                    title="清除该股票的所有新闻"
                  >
                    {clearNewsMutation.isPending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>清除中...</span>
                      </>
                    ) : (
                      <>
                        <Trash2 className="w-4 h-4" />
                        <span>清除数据</span>
                      </>
                    )}
                  </Button>
                )}
                
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
                {crawlTask.status === 'running' || crawlTask.status === 'pending' ? (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled
                      className="gap-2"
                    >
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>爬取中...</span>
                      {crawlTask.progress && (
                        <span className="text-xs text-gray-500">
                          {crawlTask.progress.message || `${crawlTask.progress.current}%`}
                        </span>
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleStopCrawl}
                      className="gap-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50"
                    >
                      <StopCircle className="w-4 h-4" />
                      <span>停止</span>
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleStartCrawl}
                    disabled={targetedCrawlMutation.isPending}
                    className="gap-2"
                  >
                    <Download className="w-4 h-4" />
                    {hasHistoryNews ? '更新爬取' : '定向爬取'}
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {newsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
              </div>
            ) : newsList && newsList.length > 0 ? (
              newsExpanded ? (
                <div className="space-y-4">
                  {/* 卡片 Grid 布局 */}
                  <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                  {displayedNews.map((news) => (
                    <Card
                      key={news.id}
                      className={getNewsCardStyle(news.sentiment_score)}
                      onClick={() => {
                        setSelectedNewsId(news.id)
                        setDrawerOpen(true)
                      }}
                    >
                      <CardHeader className="pb-2 flex-shrink-0">
                        <CardTitle className="text-sm leading-tight font-semibold text-gray-900 line-clamp-2 min-h-[40px]">
                          {news.title}
                        </CardTitle>
                        <div className="flex items-center gap-2 text-xs text-gray-500 mt-1">
                          <Calendar className="w-3 h-3" />
                          <span>{news.publish_time ? formatRelativeTime(news.publish_time) : '时间未知'}</span>
                          <span>•</span>
                          <span>{news.source}</span>
                        </div>
                      </CardHeader>
                      
                      <CardContent className="flex-1 flex flex-col pb-3 pt-1 overflow-hidden">
                        <p 
                          className="text-sm text-gray-600 leading-relaxed flex-1"
                          style={{
                            display: '-webkit-box',
                            WebkitLineClamp: 3,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden'
                          }}
                        >
                          {news.content}
                        </p>
                        
                        {/* 底部标签区域 */}
                        <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-100">
                          <div className="flex items-center gap-1.5">
                            {news.sentiment_score !== null && (
                              <Badge 
                                className={`text-xs px-2 py-0.5 ${
                                  news.sentiment_score > 0.1 ? 'bg-emerald-100 text-emerald-700 border-emerald-200' :
                                  news.sentiment_score < -0.1 ? 'bg-rose-100 text-rose-700 border-rose-200' :
                                  'bg-amber-100 text-amber-700 border-amber-200'
                                }`}
                              >
                                {news.sentiment_score > 0.1 ? '📈 利好' : 
                                 news.sentiment_score < -0.1 ? '📉 利空' : '➖ 中性'}
                              </Badge>
                            )}
                            {news.has_analysis && (
                              <Badge variant="outline" className="text-xs px-2 py-0.5">
                                已分析
                              </Badge>
                            )}
                          </div>
                          {news.sentiment_score !== null && (
                            <span className="text-xs text-gray-400">
                              {news.sentiment_score > 0 ? '+' : ''}{news.sentiment_score.toFixed(2)}
                            </span>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
                
                  {/* 继续扩展按钮 */}
                  {hasMoreNews && (
                    <div className="text-center pt-4">
                      <Button
                        variant="outline"
                        onClick={() => setNewsDisplayCount(prev => prev + 12)}
                        className="gap-2 hover:bg-blue-50"
                      >
                        <ChevronDown className="w-4 h-4" />
                        继续扩展 (还有 {(newsList?.length || 0) - newsDisplayCount} 条)
                      </Button>
                    </div>
                  )}
                  
                  {/* 已显示全部提示 */}
                  {!hasMoreNews && newsList && newsList.length > 12 && (
                    <div className="text-center pt-4 text-sm text-gray-400">
                      已显示全部 {newsList.length} 条新闻
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <p className="text-sm">新闻已折叠，点击"展开"查看</p>
                </div>
              )
            ) : (
              <div className="text-center py-12 text-gray-500">
                <Newspaper className="w-12 h-12 mx-auto opacity-50 mb-3" />
                <p>暂无关联新闻</p>
                <p className="text-sm mt-1">点击「{hasHistoryNews ? '更新爬取' : '定向爬取'}」获取该股票的相关新闻</p>
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
              <div className="flex flex-col gap-4">
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
                    disabled={isStreaming || debateMutation.isPending}
                    className="bg-gradient-to-r from-emerald-500 to-rose-500 hover:from-emerald-600 hover:to-rose-600"
                  >
                    {isStreaming || debateMutation.isPending ? (
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
                {/* 辩论模式选择器 */}
                <div className="flex items-center gap-3 pt-2 border-t border-gray-100">
                  <span className="text-sm text-gray-500">分析模式:</span>
                  <DebateModeSelector
                    value={debateMode}
                    onChange={setDebateMode}
                    disabled={debateMutation.isPending}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 流式辩论进行中 - 实时显示内容 */}
          {isStreaming && (
            <>
              {/* 阶段指示器 - 仅非聊天室模式显示 */}
              {debateMode !== 'realtime_debate' && (
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                    <span className="text-sm text-blue-600 font-medium">
                      {streamPhase === 'start' && '正在初始化...'}
                      {streamPhase === 'data_collection' && '📊 数据专员正在搜集资料...'}
                      {streamPhase === 'analyzing' && '🚀 快速分析中...'}
                      {streamPhase === 'parallel_analysis' && '⚡ Bull/Bear 并行分析中...'}
                      {streamPhase === 'debate' && '🎭 多空辩论进行中...'}
                      {streamPhase === 'decision' && '⚖️ 投资经理正在做最终决策...'}
                      {streamPhase === 'complete' && '✅ 分析完成'}
                    </span>
                  </div>
                </div>
              )}

              {/* 快速分析模式 - 流式显示 */}
              {debateMode === 'quick_analysis' && (
                <Card className="bg-gradient-to-r from-blue-50 to-cyan-50 border-none">
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-blue-700">
                      <div className={`w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center ${activeAgent === 'QuickAnalyst' ? 'animate-pulse ring-2 ring-blue-400' : ''}`}>
                        <Activity className="w-5 h-5 text-blue-600" />
                      </div>
                      🚀 快速分析
                      {activeAgent === 'QuickAnalyst' && <span className="text-xs bg-blue-200 px-2 py-0.5 rounded animate-pulse">输出中...</span>}
                    </CardTitle>
                    <CardDescription>
                      <Bot className="w-3 h-3 inline mr-1" />
                      QuickAnalyst · 快速分析师
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {streamingContent.quick ? (
                      <div className="prose prose-sm max-w-none prose-headings:text-blue-800">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {streamingContent.quick}
                        </ReactMarkdown>
                        {activeAgent === 'QuickAnalyst' && <span className="inline-block w-2 h-4 bg-blue-500 animate-pulse ml-1" />}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                        <Loader2 className="w-10 h-10 animate-spin text-blue-500 mb-4" />
                        <p className="text-sm font-medium">等待分析开始...</p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* 实时辩论模式 - 聊天室界面 */}
              {debateMode === 'realtime_debate' && (
                <DebateChatRoom
                  messages={chatMessages}
                  onSendMessage={handleUserSendMessage}
                  isDebating={isStreaming}
                  currentRound={currentRound}
                  activeAgent={activeAgent}
                  stockName={stockName}
                    historySessions={historySessions}
                    onLoadSession={(sessionId) => {
                      const session = loadSession(stockCode, sessionId)
                      if (session) {
                        setChatMessages(session.messages)
                        toast.success('已加载历史会话')
                      }
                    }}
                    onClearHistory={() => {
                      clearStockHistory(stockCode)
                      toast.success('已清除历史记录')
                    }}
                    onConfirmSearch={handleConfirmSearch}
                    onCancelSearch={handleCancelSearch}
                />
              )}

              {/* 并行模式 - 分栏显示 */}
              {debateMode === 'parallel' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* 看多观点 - 流式 */}
                  <Card className={`bg-white/90 border-l-4 border-l-emerald-500 ${activeAgent === 'BullResearcher' ? 'ring-2 ring-emerald-400' : ''}`}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <CardTitle className="flex items-center gap-2 text-emerald-700">
                            <div className={`w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center ${activeAgent === 'BullResearcher' ? 'animate-pulse' : ''}`}>
                              <ThumbsUp className="w-4 h-4 text-emerald-600" />
                            </div>
                            看多观点
                            {activeAgent === 'BullResearcher' && <span className="text-xs bg-emerald-200 px-2 py-0.5 rounded animate-pulse">输出中...</span>}
                          </CardTitle>
                          <CardDescription>
                            <Bot className="w-3 h-3 inline mr-1" />
                            BullResearcher · 看多研究员
                          </CardDescription>
                        </div>
                        {/* 操作按钮组 */}
                        {streamingContent.bull && (
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCopyContent(streamingContent.bull, '看多观点')}
                              className="h-8 px-2"
                              title="复制"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleExportToFile(
                                streamingContent.bull, 
                                `${stockName}_看多观点_${new Date().toISOString().slice(0,10)}.md`
                              )}
                              className="h-8 px-2"
                              title="导出"
                            >
                              <FileDown className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handleStartDebate}
                              disabled={isStreaming}
                              className="h-8 px-2"
                              title="重新生成"
                            >
                              <RefreshCw className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {streamingContent.bull ? (
                        <div className="prose prose-sm max-w-none prose-headings:text-emerald-800 max-h-96 overflow-y-auto">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {streamingContent.bull}
                          </ReactMarkdown>
                          {activeAgent === 'BullResearcher' && <span className="inline-block w-2 h-4 bg-emerald-500 animate-pulse ml-1" />}
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                          <Loader2 className="w-8 h-8 animate-spin text-emerald-500 mb-4" />
                          <p className="text-sm">等待分析...</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* 看空观点 - 流式 */}
                  <Card className={`bg-white/90 border-l-4 border-l-rose-500 ${activeAgent === 'BearResearcher' ? 'ring-2 ring-rose-400' : ''}`}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <CardTitle className="flex items-center gap-2 text-rose-700">
                            <div className={`w-8 h-8 rounded-full bg-rose-100 flex items-center justify-center ${activeAgent === 'BearResearcher' ? 'animate-pulse' : ''}`}>
                              <ThumbsDown className="w-4 h-4 text-rose-600" />
                            </div>
                            看空观点
                            {activeAgent === 'BearResearcher' && <span className="text-xs bg-rose-200 px-2 py-0.5 rounded animate-pulse">输出中...</span>}
                          </CardTitle>
                          <CardDescription>
                            <Bot className="w-3 h-3 inline mr-1" />
                            BearResearcher · 看空研究员
                          </CardDescription>
                        </div>
                        {/* 操作按钮组 */}
                        {streamingContent.bear && (
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCopyContent(streamingContent.bear, '看空观点')}
                              className="h-8 px-2"
                              title="复制"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleExportToFile(
                                streamingContent.bear, 
                                `${stockName}_看空观点_${new Date().toISOString().slice(0,10)}.md`
                              )}
                              className="h-8 px-2"
                              title="导出"
                            >
                              <FileDown className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handleStartDebate}
                              disabled={isStreaming}
                              className="h-8 px-2"
                              title="重新生成"
                            >
                              <RefreshCw className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {streamingContent.bear ? (
                        <div className="prose prose-sm max-w-none prose-headings:text-rose-800 max-h-96 overflow-y-auto">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {streamingContent.bear}
                          </ReactMarkdown>
                          {activeAgent === 'BearResearcher' && <span className="inline-block w-2 h-4 bg-rose-500 animate-pulse ml-1" />}
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center py-12 text-gray-500">
                          <Loader2 className="w-8 h-8 animate-spin text-rose-500 mb-4" />
                          <p className="text-sm">等待分析...</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* 投资经理决策 - 流式 */}
                  <Card className={`lg:col-span-2 bg-gradient-to-r from-blue-50 to-indigo-50 border-none ${activeAgent === 'InvestmentManager' ? 'ring-2 ring-indigo-400' : ''}`}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <CardTitle className="flex items-center gap-2 text-indigo-700">
                            <div className={`w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center ${activeAgent === 'InvestmentManager' ? 'animate-pulse' : ''}`}>
                              <Scale className="w-5 h-5 text-indigo-600" />
                            </div>
                            投资经理决策
                            {activeAgent === 'InvestmentManager' && <span className="text-xs bg-indigo-200 px-2 py-0.5 rounded animate-pulse">决策中...</span>}
                          </CardTitle>
                          <CardDescription>
                            <Bot className="w-3 h-3 inline mr-1" />
                            InvestmentManager · 投资经理
                          </CardDescription>
                        </div>
                        {/* 操作按钮组 */}
                        {streamingContent.manager && (
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCopyContent(streamingContent.manager, '投资经理决策')}
                              className="h-8 px-2"
                              title="复制"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleExportToFile(
                                streamingContent.manager, 
                                `${stockName}_投资经理决策_${new Date().toISOString().slice(0,10)}.md`
                              )}
                              className="h-8 px-2"
                              title="导出"
                            >
                              <FileDown className="w-3.5 h-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handleStartDebate}
                              disabled={isStreaming}
                              className="h-8 px-2"
                              title="重新生成"
                            >
                              <RefreshCw className="w-3.5 h-3.5" />
                            </Button>
                          </div>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {streamingContent.manager ? (
                        <div className="prose prose-sm max-w-none prose-headings:text-indigo-800">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {streamingContent.manager}
                          </ReactMarkdown>
                          {activeAgent === 'InvestmentManager' && <span className="inline-block w-2 h-4 bg-indigo-500 animate-pulse ml-1" />}
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center py-8 text-gray-500">
                          <Loader2 className="w-10 h-10 animate-spin text-indigo-500 mb-4" />
                          <p className="text-sm font-medium">等待多空分析完成后进行决策...</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              )}
            </>
          )}

          {/* 辩论结果 */}
          {!debateMutation.isPending && debateResult && debateResult.success && (
            <>
              {/* 快速分析结果 */}
              {debateResult.mode === 'quick_analysis' && debateResult.quick_analysis && (
                <Card className="bg-gradient-to-br from-blue-50 to-cyan-50 border-blue-200">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-blue-800">
                      <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                        <Activity className="w-5 h-5 text-blue-600" />
                      </div>
                      🚀 快速分析结果
                    </CardTitle>
                    <CardDescription className="flex items-center gap-4">
                      <span>
                        <Bot className="w-3 h-3 inline mr-1" />
                        QuickAnalyst · 快速分析师
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
                        {debateResult.quick_analysis.analysis || '分析完成'}
                      </ReactMarkdown>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* 实时辩论结果 - 显示聊天室 */}
              {debateResult.mode === 'realtime_debate' && chatMessages.length > 0 && (
                <div className="space-y-4">
                  <DebateChatRoom
                    messages={chatMessages}
                    onSendMessage={handleUserSendMessage}
                    isDebating={false}
                    currentRound={null}
                    activeAgent={null}
                    stockName={stockName}
                    historySessions={historySessions}
                    onLoadSession={(sessionId) => {
                      const session = loadSession(stockCode, sessionId)
                      if (session) {
                        setChatMessages(session.messages)
                        toast.success('已加载历史会话')
                      }
                    }}
                    onClearHistory={() => {
                      clearStockHistory(stockCode)
                      toast.success('已清除历史记录')
                    }}
                    onConfirmSearch={handleConfirmSearch}
                    onCancelSearch={handleCancelSearch}
                  />
                  {/* 投资经理决策摘要 */}
                  {debateResult.final_decision && (
                    <Card className="bg-gradient-to-br from-blue-50 to-purple-50 border-blue-200">
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-blue-800">
                          <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                            <Scale className="w-5 h-5 text-blue-600" />
                          </div>
                          📊 投资决策摘要
                          {debateResult.final_decision?.rating && (
                            <Badge 
                              className={`ml-2 ${
                                debateResult.final_decision.rating === '强烈推荐' || debateResult.final_decision.rating === '推荐'
                                  ? 'bg-emerald-500' 
                                  : debateResult.final_decision.rating === '中性'
                                  ? 'bg-amber-500'
                                  : 'bg-rose-500'
                              }`}
                            >
                              {debateResult.final_decision.rating}
                            </Badge>
                          )}
                        </CardTitle>
                      </CardHeader>
                    </Card>
                  )}
                </div>
              )}

              {/* 并行分析结果 */}
              {(debateResult.mode === 'parallel' || !debateResult.mode) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* 看多观点 */}
                  <Card className="bg-white/90 border-l-4 border-l-emerald-500">
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <CardTitle className="flex items-center gap-2 text-emerald-700">
                            <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center">
                              <ThumbsUp className="w-4 h-4 text-emerald-600" />
                            </div>
                            看多观点
                          </CardTitle>
                          <CardDescription>
                            <Bot className="w-3 h-3 inline mr-1" />
                            {debateResult.bull_analysis?.agent_name || 'BullResearcher'} · {debateResult.bull_analysis?.agent_role || '看多研究员'}
                          </CardDescription>
                        </div>
                        {/* 操作按钮组 */}
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCopyContent(debateResult.bull_analysis?.analysis || '', '看多观点')}
                            className="h-8 px-2"
                            title="复制"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleExportToFile(
                              debateResult.bull_analysis?.analysis || '', 
                              `${stockName}_看多观点_${new Date().toISOString().slice(0,10)}.md`
                            )}
                            className="h-8 px-2"
                            title="导出"
                          >
                            <FileDown className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleStartDebate}
                            className="h-8 px-2"
                            title="重新生成"
                          >
                            <RefreshCw className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>
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
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <CardTitle className="flex items-center gap-2 text-rose-700">
                            <div className="w-8 h-8 rounded-full bg-rose-100 flex items-center justify-center">
                              <ThumbsDown className="w-4 h-4 text-rose-600" />
                            </div>
                            看空观点
                          </CardTitle>
                          <CardDescription>
                            <Bot className="w-3 h-3 inline mr-1" />
                            {debateResult.bear_analysis?.agent_name || 'BearResearcher'} · {debateResult.bear_analysis?.agent_role || '看空研究员'}
                          </CardDescription>
                        </div>
                        {/* 操作按钮组 */}
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCopyContent(debateResult.bear_analysis?.analysis || '', '看空观点')}
                            className="h-8 px-2"
                            title="复制"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleExportToFile(
                              debateResult.bear_analysis?.analysis || '', 
                              `${stockName}_看空观点_${new Date().toISOString().slice(0,10)}.md`
                            )}
                            className="h-8 px-2"
                            title="导出"
                          >
                            <FileDown className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleStartDebate}
                            className="h-8 px-2"
                            title="重新生成"
                          >
                            <RefreshCw className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>
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
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
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
                              {debateResult.final_decision?.agent_name || 'InvestmentManager'} · {debateResult.final_decision?.agent_role || '投资经理'}
                            </span>
                            {debateResult.execution_time && (
                              <span className="text-xs bg-blue-100 px-2 py-0.5 rounded">
                                耗时 {debateResult.execution_time.toFixed(1)}s
                              </span>
                            )}
                          </CardDescription>
                        </div>
                        {/* 操作按钮组 */}
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCopyContent(debateResult.final_decision?.decision || '', '投资经理决策')}
                            className="h-8 px-2"
                            title="复制"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleExportToFile(
                              debateResult.final_decision?.decision || '', 
                              `${stockName}_投资经理决策_${new Date().toISOString().slice(0,10)}.md`
                            )}
                            className="h-8 px-2"
                            title="导出"
                          >
                            <FileDown className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleStartDebate}
                            className="h-8 px-2"
                            title="重新生成"
                          >
                            <RefreshCw className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>
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
            </>
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
      
      {/* 历史记录侧边栏 */}
      <DebateHistorySidebar
        sessions={historySessions}
        currentSessionId={currentSession?.id}
        onLoadSession={(session) => {
          restoreSessionState(session)
          setShowHistorySidebar(false)
          toast.success(`已加载历史会话：${session.mode === 'realtime_debate' ? '实时辩论' : session.mode === 'parallel' ? '并行分析' : '快速分析'}`)
        }}
        onDeleteSession={(sessionId) => {
          deleteSession(stockCode, sessionId)
          toast.success('已删除会话')
        }}
        onClearHistory={() => {
          clearStockHistory(stockCode)
          setDebateResult(null)
          setStreamingContent({ bull: '', bear: '', manager: '', quick: '' })
          setChatMessages([])
          toast.success('已清除所有历史记录')
        }}
        isOpen={showHistorySidebar}
        onToggle={() => setShowHistorySidebar(!showHistorySidebar)}
      />
    </div>
  )
}
