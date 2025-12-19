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
    console.error('API Error:', error.response?.data || error.message)
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
}

/**
 * 智能体相关 API - Phase 2
 */
export const agentApi = {
  /**
   * 触发股票辩论分析
   * 注意：辩论分析需要多次LLM调用，耗时较长（可能2-5分钟）
   */
  runDebate: async (request: DebateRequest): Promise<DebateResponse> => {
    const response = await apiClient.post<DebateResponse>('/agents/debate', request, {
      timeout: 300000  // 5分钟超时，因为辩论需要多次LLM调用
    })
    return response.data
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
   * 清空执行日志（仅开发用）
   */
  clearLogs: async (): Promise<{ message: string }> => {
    const response = await apiClient.delete('/agents/logs')
    return response.data
  },
}

export { apiClient }
export default apiClient

