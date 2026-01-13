import axios from 'axios'
import type {
  News,
  Analysis,
  CrawlTask,
  TaskStats,
  CrawlRequest,
  CrawlResponse,
  AnalysisResponse,
  StockOverview,
  StockNewsItem,
  SentimentTrendPoint,
  KLineDataPoint,
  RealtimeQuote,
  DebateRequest,
  DebateResponse,
  AgentLogEntry,
  AgentMetrics,
  AgentInfo,
  WorkflowInfo,
} from '@/types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    // 可以在这里添加认证 token
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 详细的错误日志
    if (error.response) {
      // 服务器返回了错误响应
      console.error('API Error Response:', {
        status: error.response.status,
        statusText: error.response.statusText,
        data: error.response.data,
        url: error.config?.url,
      })
    } else if (error.request) {
      // 请求已发出但没有收到响应
      console.error('API Error Request:', {
        message: error.message,
        url: error.config?.url,
        baseURL: error.config?.baseURL,
        timeout: error.code === 'ECONNABORTED' ? 'Request timeout' : 'Network error',
      })
    } else {
      // 请求配置出错
      console.error('API Error Config:', error.message)
    }
    return Promise.reject(error)
  }
)

/**
 * 新闻相关 API - Phase 2 升级版
 */
export const newsApi = {
  /**
   * Phase 2: 获取最新新闻（智能缓存 + 自动刷新）
   */
  getLatestNews: async (params?: {
    source?: string
    limit?: number
    force_refresh?: boolean
  }): Promise<News[]> => {
    const response = await apiClient.get<any>('/news/latest', { params })
    // Phase 2 API 返回 { success, data: News[], ... }
    // 兼容处理：如果返回的是对象，提取 data 字段；否则直接返回
    if (response.data && typeof response.data === 'object' && 'data' in response.data) {
      return response.data.data
    }
    return response.data
  },

  /**
   * Phase 2: 强制刷新新闻
   */
  forceRefresh: async (params: { source: string }): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.post('/news/refresh', null, { params })
    return response.data
  },

  /**
   * 获取新闻列表（带筛选）
   */
  getNewsList: async (params?: {
    skip?: number
    limit?: number
    source?: string
    sentiment?: string
  }): Promise<News[]> => {
    const response = await apiClient.get<News[]>('/news/', { params })
    return response.data
  },

  /**
   * 获取新闻详情
   */
  getNewsDetail: async (newsId: number): Promise<News> => {
    const response = await apiClient.get<News>(`/news/${newsId}`)
    return response.data
  },

  /**
   * 获取新闻原始 HTML
   */
  getNewsHtml: async (newsId: number): Promise<{ id: number; title: string; url: string; raw_html: string | null; has_raw_html: boolean }> => {
    const response = await apiClient.get(`/news/${newsId}/html`)
    return response.data
  },

  /**
   * 【已废弃】触发爬取
   */
  crawlNews: async (data: CrawlRequest): Promise<CrawlResponse> => {
    console.warn('⚠️ crawlNews API 已废弃，请使用 forceRefresh')
    const response = await apiClient.post<CrawlResponse>('/news/crawl', data)
    return response.data
  },

  /**
   * 删除新闻
   */
  deleteNews: async (newsId: number): Promise<void> => {
    await apiClient.delete(`/news/${newsId}`)
  },

  /**
   * 批量删除新闻
   */
  batchDeleteNews: async (newsIds: number[]): Promise<{ success: boolean; message: string; deleted_count: number }> => {
    const response = await apiClient.post('/news/batch/delete', { news_ids: newsIds })
    return response.data
  },
}

/**
 * 分析相关 API
 */
export const analysisApi = {
  /**
   * 触发新闻分析
   * @param newsId - 新闻ID
   * @param config - 可选的LLM配置 (provider和model)
   */
  analyzeNews: async (
    newsId: number, 
    config?: { provider?: string; model?: string }
  ): Promise<AnalysisResponse> => {
    const response = await apiClient.post<AnalysisResponse>(
      `/analysis/news/${newsId}`,
      config || {}
    )
    return response.data
  },

  /**
   * 获取分析详情
   */
  getAnalysisDetail: async (analysisId: number): Promise<Analysis> => {
    const response = await apiClient.get<Analysis>(`/analysis/${analysisId}`)
    return response.data
  },

  /**
   * 获取新闻的所有分析结果
   */
  getNewsAnalyses: async (newsId: number): Promise<Analysis[]> => {
    const response = await apiClient.get<Analysis[]>(`/analysis/news/${newsId}/all`)
    return response.data
  },

  /**
   * 批量分析新闻
   * 注意：批量分析可能需要较长时间，超时时间设置为5分钟
   */
  batchAnalyzeNews: async (
    newsIds: number[],
    config?: { provider?: string; model?: string }
  ): Promise<{ success: boolean; message: string; total_count: number; success_count: number; failed_count: number }> => {
    // 确保newsIds是有效的数组
    if (!Array.isArray(newsIds) || newsIds.length === 0) {
      throw new Error('newsIds must be a non-empty array')
    }
    
    const requestBody: { news_ids: number[]; provider?: string; model?: string } = {
      news_ids: newsIds
    }
    
    // 只有当config存在且值不为undefined和空字符串时才添加到请求体
    if (config) {
      if (config.provider !== undefined && config.provider !== null && config.provider !== '') {
        requestBody.provider = config.provider
      }
      if (config.model !== undefined && config.model !== null && config.model !== '') {
        requestBody.model = config.model
      }
    }
    
    // 批量分析可能需要较长时间，设置5分钟超时
    const response = await apiClient.post('/analysis/news/batch', requestBody, {
      timeout: 5 * 60 * 1000  // 5分钟超时
    })
    return response.data
  },
}

/**
 * LLM 配置相关类型
 */
export interface ModelInfo {
  value: string
  label: string
  description: string
}

export interface ProviderInfo {
  value: string
  label: string
  icon: string
  models: ModelInfo[]
  has_api_key: boolean
}

export interface LLMConfigResponse {
  default_provider: string
  default_model: string
  providers: ProviderInfo[]
}

/**
 * LLM 配置相关 API
 */
export const llmApi = {
  /**
   * 获取 LLM 配置（可用厂商和模型列表）
   */
  getConfig: async (): Promise<LLMConfigResponse> => {
    const response = await apiClient.get<LLMConfigResponse>('/llm/config')
    return response.data
  },
}

/**
 * 任务相关 API
 */
export const taskApi = {
  /**
   * 获取任务列表
   */
  getTaskList: async (params?: {
    skip?: number
    limit?: number
    mode?: string
    status?: string
  }): Promise<CrawlTask[]> => {
    const response = await apiClient.get<CrawlTask[]>('/tasks/', { params })
    return response.data
  },

  /**
   * 获取任务详情
   */
  getTaskDetail: async (taskId: number): Promise<CrawlTask> => {
    const response = await apiClient.get<CrawlTask>(`/tasks/${taskId}`)
    return response.data
  },

  /**
   * 触发冷启动
   */
  triggerColdStart: async (data: {
    source: string
    start_page: number
    end_page: number
  }): Promise<{ success: boolean; message: string; celery_task_id?: string }> => {
    const response = await apiClient.post('/tasks/cold-start', data)
    return response.data
  },

  /**
   * 获取任务统计
   */
  getTaskStats: async (): Promise<TaskStats> => {
    const response = await apiClient.get<TaskStats>('/tasks/stats/summary')
    return response.data
  },
}

/**
 * 股票分析相关 API - Phase 2
 */
export const stockApi = {
  /**
   * 获取股票概览信息
   */
  getOverview: async (stockCode: string): Promise<StockOverview> => {
    const response = await apiClient.get<StockOverview>(`/stocks/${stockCode}`)
    return response.data
  },

  /**
   * 获取股票关联新闻
   */
  getNews: async (stockCode: string, params?: {
    limit?: number
    offset?: number
    sentiment?: 'positive' | 'negative' | 'neutral'
  }): Promise<StockNewsItem[]> => {
    const response = await apiClient.get<StockNewsItem[]>(`/stocks/${stockCode}/news`, { params })
    return response.data
  },

  /**
   * 获取情感趋势
   */
  getSentimentTrend: async (stockCode: string, days: number = 30): Promise<SentimentTrendPoint[]> => {
    const response = await apiClient.get<SentimentTrendPoint[]>(
      `/stocks/${stockCode}/sentiment-trend`,
      { params: { days } }
    )
    return response.data
  },

  /**
   * 获取K线数据（真实数据，使用 akshare）
   * @param stockCode 股票代码
   * @param period 周期：daily, 1m, 5m, 15m, 30m, 60m
   * @param limit 数据条数
   * @param adjust 复权类型：qfq=前复权, hfq=后复权, ""=不复权
   */
  getKLineData: async (
    stockCode: string, 
    period: 'daily' | '1m' | '5m' | '15m' | '30m' | '60m' = 'daily',
    limit: number = 90,
    adjust: 'qfq' | 'hfq' | '' = 'qfq'
  ): Promise<KLineDataPoint[]> => {
    const response = await apiClient.get<KLineDataPoint[]>(
      `/stocks/${stockCode}/kline`,
      { params: { period, limit, adjust } }
    )
    return response.data
  },

  /**
   * 获取实时行情
   */
  getRealtimeQuote: async (stockCode: string): Promise<RealtimeQuote | null> => {
    const response = await apiClient.get<RealtimeQuote | null>(
      `/stocks/${stockCode}/realtime`
    )
    return response.data
  },

  /**
   * 搜索股票（从数据库）
   */
  searchRealtime: async (query: string, limit: number = 20): Promise<Array<{
    code: string
    name: string
    full_code: string
    market: string | null
    industry: string | null
  }>> => {
    const response = await apiClient.get('/stocks/search/realtime', {
      params: { q: query, limit }
    })
    return response.data
  },

  /**
   * 初始化股票数据（从 akshare 获取并存入数据库）
   */
  initStockData: async (): Promise<{
    success: boolean
    message: string
    count: number
  }> => {
    const response = await apiClient.post('/stocks/init')
    return response.data
  },

  /**
   * 获取数据库中的股票数量
   */
  getStockCount: async (): Promise<{ count: number; message: string }> => {
    const response = await apiClient.get('/stocks/count')
    return response.data
  },

  /**
   * 从数据库搜索股票
   */
  search: async (query: string, limit: number = 10): Promise<Array<{
    code: string
    name: string
    full_code: string | null
    industry: string | null
  }>> => {
    const response = await apiClient.get('/stocks/search/code', {
      params: { q: query, limit }
    })
    return response.data
  },

  /**
   * 触发定向爬取任务
   */
  startTargetedCrawl: async (
    stockCode: string,
    stockName: string,
    days: number = 30
  ): Promise<{
    success: boolean
    message: string
    task_id?: number
    celery_task_id?: string
  }> => {
    const response = await apiClient.post(`/stocks/${stockCode}/targeted-crawl`, {
      stock_name: stockName,
      days
    })
    return response.data
  },

  /**
   * 查询定向爬取任务状态
   */
  getTargetedCrawlStatus: async (stockCode: string): Promise<{
    task_id?: number
    status: string
    celery_task_id?: string
    progress?: {
      current: number
      total: number
      message?: string
    }
    crawled_count?: number
    saved_count?: number
    error_message?: string
    execution_time?: number
    started_at?: string
    completed_at?: string
  }> => {
    const response = await apiClient.get(`/stocks/${stockCode}/targeted-crawl/status`)
    return response.data
  },

  /**
   * 取消定向爬取任务
   */
  cancelTargetedCrawl: async (stockCode: string): Promise<{
    success: boolean
    message: string
    task_id?: number
  }> => {
    const response = await apiClient.post(`/stocks/${stockCode}/targeted-crawl/cancel`)
    return response.data
  },

  /**
   * 清除股票新闻
   */
  clearStockNews: async (stockCode: string): Promise<{
    success: boolean
    message: string
    deleted_count?: number
  }> => {
    const response = await apiClient.delete(`/stocks/${stockCode}/news`)
    return response.data
  },
}

/**
 * 知识图谱 API
 */
export const knowledgeGraphApi = {
  /**
   * 获取公司知识图谱
   */
  getCompanyGraph: async (stockCode: string): Promise<{
    stock_code: string
    stock_name: string
    graph_exists: boolean
    stats?: Record<string, number>
    name_variants: string[]
    businesses: Array<{
      name: string
      type: string
      status: string
      description?: string
    }>
    industries: string[]
    products: string[]
    concepts: string[]
    search_queries: string[]
  }> => {
    const response = await apiClient.get(`/knowledge-graph/${stockCode}`)
    return response.data
  },

  /**
   * 构建公司知识图谱
   */
  buildGraph: async (stockCode: string, forceRebuild: boolean = false): Promise<{
    success: boolean
    message: string
    graph_stats?: Record<string, number>
  }> => {
    const response = await apiClient.post(`/knowledge-graph/${stockCode}/build`, {
      force_rebuild: forceRebuild
    })
    return response.data
  },

  /**
   * 更新公司知识图谱
   */
  updateGraph: async (stockCode: string): Promise<{
    success: boolean
    message: string
    graph_stats?: Record<string, number>
  }> => {
    const response = await apiClient.post(`/knowledge-graph/${stockCode}/update`, {
      update_from_news: true,
      news_limit: 20
    })
    return response.data
  },

  /**
   * 删除公司知识图谱
   */
  deleteGraph: async (stockCode: string): Promise<{
    success: boolean
    message: string
  }> => {
    const response = await apiClient.delete(`/knowledge-graph/${stockCode}`)
    return response.data
  },
}

/**
 * 智能体相关 API - Phase 2
 */
// SSE 事件类型
export interface SSEDebateEvent {
  type: 'phase' | 'agent' | 'progress' | 'result' | 'error' | 'complete' | 'task_plan'
  data: {
    phase?: string
    message?: string
    agent?: string
    role?: string
    content?: string
    is_chunk?: boolean
    is_start?: boolean
    is_end?: boolean
    round?: number
    max_rounds?: number
    success?: boolean
    mode?: string
    bull_analysis?: any
    bear_analysis?: any
    final_decision?: any
    quick_analysis?: any
    debate_id?: string
    execution_time?: number
    total_rounds?: number
    debate_history?: any[]
  }
}

export const agentApi = {
  /**
   * 触发股票辩论分析（非流式）
   * 注意：辩论分析需要多次LLM调用，耗时较长（可能2-5分钟）
   */
  runDebate: async (request: DebateRequest): Promise<DebateResponse> => {
    const response = await apiClient.post<DebateResponse>('/agents/debate', request, {
      timeout: 300000  // 5分钟超时，因为辩论需要多次LLM调用
    })
    return response.data
  },

  /**
   * 流式辩论分析（SSE）
   * 使用 Server-Sent Events 实时推送辩论过程
   */
  runDebateStream: (
    request: DebateRequest,
    onEvent: (event: SSEDebateEvent) => void,
    onError?: (error: Error) => void,
    onComplete?: () => void
  ): (() => void) => {
    const controller = new AbortController()
    
    // 使用 fetch 发送 POST 请求并处理 SSE 响应
    fetch(`${API_BASE_URL}/agents/debate/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        
        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }
        
        const decoder = new TextDecoder()
        let buffer = ''
        
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          
          buffer += decoder.decode(value, { stream: true })
          
          // 解析 SSE 事件
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // 保留未完成的行
          
          let currentEvent = ''
          let currentData = ''
          
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7)
            } else if (line.startsWith('data: ')) {
              currentData = line.slice(6)
            } else if (line === '' && currentEvent && currentData) {
              // 完整的事件
              try {
                const data = JSON.parse(currentData)
                onEvent({ type: currentEvent as SSEDebateEvent['type'], data })
              } catch (e) {
                console.error('Failed to parse SSE data:', currentData)
              }
              currentEvent = ''
              currentData = ''
            }
          }
        }
        
        onComplete?.()
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('SSE error:', error)
          onError?.(error)
        }
      })
    
    // 返回取消函数
    return () => controller.abort()
  },

  /**
   * 辩论追问（SSE）
   * 用户可以在辩论结束后继续提问
   */
  followUp: (
    request: {
      stock_code: string
      stock_name?: string
      question: string
      target_agent?: string
      context?: string
    },
    onEvent: (event: SSEDebateEvent) => void,
    onError?: (error: Error) => void,
    onComplete?: () => void
  ): (() => void) => {
    const controller = new AbortController()
    
    fetch(`${API_BASE_URL}/agents/debate/followup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        
        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }
        
        const decoder = new TextDecoder()
        let buffer = ''
        
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          
          buffer += decoder.decode(value, { stream: true })
          
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          
          let currentEvent = ''
          let currentData = ''
          
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7)
            } else if (line.startsWith('data: ')) {
              currentData = line.slice(6)
            } else if (line === '' && currentEvent && currentData) {
              try {
                const data = JSON.parse(currentData)
                onEvent({ type: currentEvent as SSEDebateEvent['type'], data })
              } catch (e) {
                console.error('Failed to parse SSE data:', currentData)
              }
              currentEvent = ''
              currentData = ''
            }
          }
        }
        
        onComplete?.()
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('SSE error:', error)
          onError?.(error)
        }
      })
    
    return () => controller.abort()
  },

  /**
   * 获取辩论结果
   */
  getDebateResult: async (debateId: string): Promise<DebateResponse> => {
    const response = await apiClient.get<DebateResponse>(`/agents/debate/${debateId}`)
    return response.data
  },

  /**
   * 获取智能体执行日志
   */
  getLogs: async (params?: {
    limit?: number
    agent_name?: string
    status?: 'started' | 'completed' | 'failed'
  }): Promise<AgentLogEntry[]> => {
    const response = await apiClient.get<AgentLogEntry[]>('/agents/logs', { params })
    return response.data
  },

  /**
   * 获取智能体性能指标
   */
  getMetrics: async (): Promise<AgentMetrics> => {
    const response = await apiClient.get<AgentMetrics>('/agents/metrics')
    return response.data
  },

  /**
   * 获取辩论执行轨迹
   */
  getTrajectory: async (debateId: string): Promise<Array<{
    step_id: string
    step_name: string
    timestamp: string
    agent_name?: string
    output_data?: Record<string, any>
    status: string
  }>> => {
    const response = await apiClient.get(`/agents/trajectory/${debateId}`)
    return response.data
  },

  /**
   * 获取可用智能体列表
   */
  getAvailable: async (): Promise<{
    agents: AgentInfo[]
    workflows: WorkflowInfo[]
  }> => {
    const response = await apiClient.get('/agents/available')
    return response.data
  },

  /**
   * 执行搜索计划 (SSE)
   */
  executeSearch: (
    plan: any,
    onEvent: (event: SSEDebateEvent) => void,
    onError?: (error: Error) => void,
    onComplete?: () => void
  ): (() => void) => {
    const controller = new AbortController()
    
    fetch(`${API_BASE_URL}/agents/search/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ plan }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        
        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }
        
        const decoder = new TextDecoder()
        let buffer = ''
        
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          
          buffer += decoder.decode(value, { stream: true })
          
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          
          let currentEvent = ''
          let currentData = ''
          
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7)
            } else if (line.startsWith('data: ')) {
              currentData = line.slice(6)
            } else if (line === '' && currentEvent && currentData) {
              try {
                const data = JSON.parse(currentData)
                onEvent({ type: currentEvent as SSEDebateEvent['type'], data })
              } catch (e) {
                console.error('Failed to parse SSE data:', currentData)
              }
              currentEvent = ''
              currentData = ''
            }
          }
        }
        
        onComplete?.()
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('SSE error:', error)
          onError?.(error)
        }
      })
    
    return () => controller.abort()
  },

  /**
   * 清空执行日志（仅开发用）
   */
  clearLogs: async (): Promise<{ message: string }> => {
    const response = await apiClient.delete('/agents/logs')
    return response.data
  },
}

/**
 * Alpha Mining 相关类型
 */
export interface AlphaMiningFactor {
  formula: number[]
  formula_str: string
  sortino: number
  sharpe?: number
  ic?: number
  discovered_at?: string
  stock_code?: string
}

export interface AlphaMiningMetrics {
  sortino_ratio: number
  sharpe_ratio: number
  ic: number
  rank_ic: number
  max_drawdown: number
  turnover: number
  total_return: number
  win_rate: number
  avg_return?: number
}

export interface MineRequest {
  stock_code?: string
  num_steps: number
  use_sentiment: boolean
  batch_size?: number
}

export interface EvaluateRequest {
  formula: string
  stock_code?: string
}

export interface SentimentCompareResult {
  best_score: number
  best_formula: string
  total_steps: number
  num_features: number
}

export interface OperatorInfo {
  name: string
  arity: number
  description: string
}

/**
 * Alpha Mining 相关 API
 */
export const alphaMiningApi = {
  /**
   * 启动因子挖掘任务（后台执行）
   */
  mine: async (request: MineRequest): Promise<{
    success: boolean
    task_id: string
    message: string
  }> => {
    const response = await apiClient.post('/alpha-mining/mine', request)
    return response.data
  },

  /**
   * SSE 流式挖掘（返回 fetch Response）
   */
  mineStream: (
    request: MineRequest,
    onProgress: (data: {
      step: number
      progress: number
      loss: number
      avg_reward: number
      max_reward: number
      valid_ratio: number
      best_score: number
      best_formula: string
    }) => void,
    onComplete: (data: { best_score: number; best_formula: string }) => void,
    onError: (error: string) => void
  ): (() => void) => {
    const controller = new AbortController()

    fetch(`${apiClient.defaults.baseURL}/alpha-mining/mine/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const reader = response.body?.getReader()
        if (!reader) throw new Error('No body')

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let event = '', data = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) event = line.slice(7)
            else if (line.startsWith('data: ')) data = line.slice(6)
            else if (line === '' && event && data) {
              try {
                const parsed = JSON.parse(data)
                if (event === 'progress') onProgress(parsed)
                else if (event === 'complete') onComplete(parsed)
                else if (event === 'error') onError(parsed.error)
              } catch {}
              event = data = ''
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') onError(err.message)
      })

    return () => controller.abort()
  },

  /**
   * 评估因子表达式
   */
  evaluate: async (request: EvaluateRequest): Promise<{
    success: boolean
    formula: string
    metrics?: AlphaMiningMetrics
    error?: string
  }> => {
    const response = await apiClient.post('/alpha-mining/evaluate', request)
    return response.data
  },

  /**
   * 生成候选因子
   */
  generate: async (batch_size: number = 10, max_len: number = 8): Promise<{
    success: boolean
    generated: number
    valid: number
    factors: Array<{
      formula: number[]
      formula_str: string
      sortino: number
      ic: number
    }>
  }> => {
    const response = await apiClient.post('/alpha-mining/generate', { batch_size, max_len })
    return response.data
  },

  /**
   * 获取已发现的因子列表
   */
  getFactors: async (top_k: number = 20, stock_code?: string): Promise<{
    success: boolean
    total: number
    returned: number
    factors: AlphaMiningFactor[]
  }> => {
    const response = await apiClient.get('/alpha-mining/factors', {
      params: { top_k, stock_code }
    })
    return response.data
  },

  /**
   * 获取任务状态
   */
  getTaskStatus: async (task_id: string): Promise<{
    task_id: string
    status: 'pending' | 'running' | 'completed' | 'failed'
    progress: number
    result?: { best_factor: string; best_score: number; total_steps: number }
    error?: string
  }> => {
    const response = await apiClient.get(`/alpha-mining/status/${task_id}`)
    return response.data
  },

  /**
   * 获取支持的操作符列表
   */
  getOperators: async (): Promise<{
    success: boolean
    features: string[]
    operators: OperatorInfo[]
  }> => {
    const response = await apiClient.get('/alpha-mining/operators')
    return response.data
  },

  /**
   * 情感融合效果对比
   */
  compareSentiment: async (num_steps: number = 50, batch_size: number = 16): Promise<{
    success: boolean
    with_sentiment: SentimentCompareResult
    without_sentiment: SentimentCompareResult
    improvement: { score_diff: number; improvement_pct: number }
  }> => {
    const response = await apiClient.post('/alpha-mining/compare-sentiment', {
      num_steps,
      batch_size
    })
    return response.data
  },

  /**
   * Agent 调用演示
   */
  agentDemo: async (params: {
    stock_code?: string
    num_steps: number
    use_sentiment: boolean
  }): Promise<{
    success: boolean
    agent_name: string
    tool_name: string
    input_params: Record<string, any>
    output: { best_formula: string; best_score: number; total_steps: number } | null
    execution_time: number
    logs: string[]
  }> => {
    const response = await apiClient.post('/alpha-mining/agent-demo', params)
    return response.data
  },

  /**
   * 删除任务
   */
  deleteTask: async (task_id: string): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.delete(`/alpha-mining/tasks/${task_id}`)
    return response.data
  },
}

export { apiClient }
export default apiClient

