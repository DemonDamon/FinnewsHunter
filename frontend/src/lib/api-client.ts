import axios from 'axios'
import type {
  News,
  Analysis,
  CrawlTask,
  TaskStats,
  CrawlRequest,
  CrawlResponse,
  AnalysisResponse,
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

export { apiClient }
export default apiClient

