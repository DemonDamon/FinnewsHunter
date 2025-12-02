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
 * 新闻相关 API
 */
export const newsApi = {
  /**
   * 获取新闻列表
   */
  getNewsList: async (params?: {
    skip?: number
    limit?: number
    source?: string
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
   * 触发爬取
   */
  crawlNews: async (data: CrawlRequest): Promise<CrawlResponse> => {
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
   */
  analyzeNews: async (newsId: number): Promise<AnalysisResponse> => {
    const response = await apiClient.post<AnalysisResponse>(`/analysis/news/${newsId}`)
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

