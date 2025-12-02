/**
 * API 类型定义
 * 与后端 API 响应结构保持一致
 */

export interface News {
  id: number
  title: string
  content: string
  url: string
  source: string
  publish_time: string | null
  created_at: string
  stock_codes: string[] | null
  sentiment_score: number | null
  author: string | null
  keywords: string[] | null
}

export interface Analysis {
  id: number
  news_id: number
  agent_name: string
  agent_role: string | null
  analysis_result: string
  summary: string | null
  sentiment: 'positive' | 'negative' | 'neutral' | null
  sentiment_score: number | null
  confidence: number | null
  execution_time: number | null
  created_at: string
}

export interface CrawlTask {
  id: number
  celery_task_id: string | null
  mode: 'cold_start' | 'realtime' | 'targeted'
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  source: string
  config: Record<string, any> | null
  progress: {
    current_page?: number
    total_pages?: number
    percentage?: number
  } | null
  current_page: number | null
  total_pages: number | null
  result: Record<string, any> | null
  crawled_count: number
  saved_count: number
  error_message: string | null
  execution_time: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface TaskStats {
  total: number
  by_status: Record<string, number>
  by_mode: Record<string, number>
  recent_completed: number
  total_news_crawled: number
  total_news_saved: number
}

export interface CrawlRequest {
  source: string
  start_page: number
  end_page: number
}

export interface CrawlResponse {
  success: boolean
  message: string
  crawled_count: number
  saved_count: number
  source: string
}

export interface AnalysisResponse {
  success: boolean
  analysis_id?: number
  news_id: number
  sentiment?: string
  sentiment_score?: number
  confidence?: number
  summary?: string
  execution_time?: number
  error?: string
}

