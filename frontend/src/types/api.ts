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

// ============ Phase 2: 个股分析类型 ============

export interface StockOverview {
  code: string
  name: string | null
  total_news: number
  analyzed_news: number
  avg_sentiment: number | null
  recent_sentiment: number | null
  sentiment_trend: 'up' | 'down' | 'stable'
  last_news_time: string | null
}

export interface StockNewsItem {
  id: number
  title: string
  content: string
  url: string
  source: string
  publish_time: string | null
  sentiment_score: number | null
  has_analysis: boolean
}

export interface SentimentTrendPoint {
  date: string
  avg_sentiment: number
  news_count: number
  positive_count: number
  negative_count: number
  neutral_count: number
}

export interface KLineDataPoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// ============ Phase 2: 智能体辩论类型 ============

export interface DebateRequest {
  stock_code: string
  stock_name?: string
  context?: string
  provider?: string
  model?: string
}

export interface AgentAnalysis {
  success: boolean
  agent_name: string
  agent_role?: string
  stance: 'bull' | 'bear'
  analysis?: string
  error?: string
  timestamp?: string
}

export interface FinalDecision {
  success: boolean
  agent_name: string
  agent_role?: string
  decision?: string
  rating?: string
  error?: string
  timestamp?: string
}

export interface TrajectoryStep {
  step: string
  timestamp: string
  data: Record<string, any>
}

export interface DebateResponse {
  success: boolean
  debate_id?: string
  stock_code: string
  stock_name?: string
  bull_analysis?: AgentAnalysis
  bear_analysis?: AgentAnalysis
  final_decision?: FinalDecision
  trajectory?: TrajectoryStep[]
  execution_time?: number
  error?: string
}

// ============ Phase 2: 智能体监控类型 ============

export interface AgentLogEntry {
  id: string
  timestamp: string
  agent_name: string
  agent_role?: string
  action: string
  status: 'started' | 'completed' | 'failed'
  details?: Record<string, any>
  execution_time?: number
}

export interface AgentMetrics {
  total_executions: number
  successful_executions: number
  failed_executions: number
  avg_execution_time: number
  agent_stats: Record<string, {
    total: number
    successful: number
    failed: number
    avg_time: number
  }>
  recent_activity: Array<{
    timestamp: string
    agent_name: string
    action: string
    status: string
  }>
}

export interface AgentInfo {
  name: string
  role: string
  description: string
  status: 'active' | 'inactive'
}

export interface WorkflowInfo {
  name: string
  description: string
  agents: string[]
  status: 'active' | 'inactive'
}

