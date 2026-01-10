import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// 聊天消息类型（与 DebateChatRoom 一致）
export type ChatRole = 'user' | 'bull' | 'bear' | 'manager' | 'system' | 'data_collector' | 'search'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  timestamp: Date
  round?: number
  isStreaming?: boolean
  mentions?: string[] // 消息中的 @ 提及
  searchPlan?: any // 搜索计划
  searchStatus?: 'pending' | 'executing' | 'completed' | 'cancelled'
}

// 分析结果（用于保存并行/快速分析模式的结果）
export interface AnalysisResult {
  bull?: string
  bear?: string
  manager?: string
  quick?: string
  finalDecision?: {
    rating?: string
    decision?: string
  }
  executionTime?: number
}

// 辩论会话
export interface DebateSession {
  id: string
  stockCode: string
  stockName: string
  messages: ChatMessage[]
  mode: string
  createdAt: Date
  updatedAt: Date
  // 新增：并行/快速分析模式的结果
  analysisResult?: AnalysisResult
  // 新增：会话状态
  status?: 'in_progress' | 'completed' | 'interrupted'
}

// 本地存储的会话格式（日期需要序列化）
interface SerializedSession {
  id: string
  stockCode: string
  stockName: string
  messages: Array<Omit<ChatMessage, 'timestamp'> & { timestamp: string }>
  mode: string
  createdAt: string
  updatedAt: string
}

interface DebateStore {
  // 当前会话
  currentSession: DebateSession | null
  // 历史会话列表（按股票代码索引）
  sessions: Record<string, DebateSession[]>
  
  // 操作方法
  startSession: (stockCode: string, stockName: string, mode: string) => string
  addMessage: (message: ChatMessage) => void
  updateMessage: (messageId: string, updates: Partial<ChatMessage>) => void
  clearCurrentSession: () => void
  
  // 批量同步消息（用于辩论完成时一次性同步所有消息）
  syncMessages: (messages: ChatMessage[]) => void
  
  // 新增：保存分析结果（用于并行/快速分析模式）
  saveAnalysisResult: (result: AnalysisResult) => void
  // 新增：更新会话状态
  updateSessionStatus: (status: 'in_progress' | 'completed' | 'interrupted') => void
  // 新增：恢复会话到页面状态
  restoreSession: (sessionId: string) => DebateSession | null
  // 新增：获取最近未完成的会话
  getLatestInProgressSession: (stockCode: string) => DebateSession | null
  
  // 历史管理
  loadSession: (stockCode: string, sessionId?: string) => DebateSession | null
  getStockSessions: (stockCode: string) => DebateSession[]
  deleteSession: (stockCode: string, sessionId: string) => void
  clearStockHistory: (stockCode: string) => Promise<void>
  
  // 同步到后端（可选）
  syncToBackend: (stockCode: string) => Promise<void>
  loadFromBackend: (stockCode: string) => Promise<void>
}

// 序列化会话（用于持久化）
const serializeSession = (session: DebateSession): SerializedSession => ({
  ...session,
  messages: session.messages.map(m => ({
    ...m,
    timestamp: m.timestamp.toISOString()
  })),
  createdAt: session.createdAt.toISOString(),
  updatedAt: session.updatedAt.toISOString()
})

// 反序列化会话（从持久化恢复）
const deserializeSession = (session: SerializedSession): DebateSession => ({
  ...session,
  messages: session.messages.map(m => ({
    ...m,
    timestamp: new Date(m.timestamp)
  })),
  createdAt: new Date(session.createdAt),
  updatedAt: new Date(session.updatedAt)
})

export const useDebateStore = create<DebateStore>()(
  persist(
    (set, get) => ({
      currentSession: null,
      sessions: {},
      
      startSession: (stockCode, stockName, mode) => {
        const sessionId = `debate-${stockCode}-${Date.now()}`
        const newSession: DebateSession = {
          id: sessionId,
          stockCode,
          stockName,
          messages: [],
          mode,
          createdAt: new Date(),
          updatedAt: new Date(),
          status: 'in_progress'
        }
        
        set(state => ({
          currentSession: newSession,
          sessions: {
            ...state.sessions,
            [stockCode]: [
              newSession,
              ...(state.sessions[stockCode] || []).slice(0, 9) // 最多保留10个历史会话
            ]
          }
        }))
        
        return sessionId
      },
      
      addMessage: (message) => {
        set(state => {
          if (!state.currentSession) return state
          
          const updatedSession = {
            ...state.currentSession,
            messages: [...state.currentSession.messages, message],
            updatedAt: new Date()
          }
          
          // 同时更新 sessions 中的记录
          const stockCode = updatedSession.stockCode
          const updatedSessions = (state.sessions[stockCode] || []).map(s =>
            s.id === updatedSession.id ? updatedSession : s
          )
          
          return {
            currentSession: updatedSession,
            sessions: {
              ...state.sessions,
              [stockCode]: updatedSessions
            }
          }
        })
      },
      
      // 批量同步消息（替换当前会话的所有消息）
      syncMessages: (messages) => {
        set(state => {
          if (!state.currentSession) return state
          
          // 优化过滤逻辑：只要有内容就保存，并强制标记为非流式
          const validMessages = messages
            .filter(m => m.content || m.searchPlan || m.role === 'system')
            .map(m => ({
              ...m,
              isStreaming: false // 强制标记为已完成
            }))
          
          const updatedSession = {
            ...state.currentSession,
            messages: validMessages,
            updatedAt: new Date()
          }
          
          const stockCode = updatedSession.stockCode
          const updatedSessions = (state.sessions[stockCode] || []).map(s =>
            s.id === updatedSession.id ? updatedSession : s
          )
          
          return {
            currentSession: updatedSession,
            sessions: {
              ...state.sessions,
              [stockCode]: updatedSessions
            }
          }
        })
      },
      
      updateMessage: (messageId, updates) => {
        set(state => {
          if (!state.currentSession) return state
          
          const updatedMessages = state.currentSession.messages.map(m =>
            m.id === messageId ? { ...m, ...updates } : m
          )
          
          const updatedSession = {
            ...state.currentSession,
            messages: updatedMessages,
            updatedAt: new Date()
          }
          
          const stockCode = updatedSession.stockCode
          const updatedSessions = (state.sessions[stockCode] || []).map(s =>
            s.id === updatedSession.id ? updatedSession : s
          )
          
          return {
            currentSession: updatedSession,
            sessions: {
              ...state.sessions,
              [stockCode]: updatedSessions
            }
          }
        })
      },
      
      clearCurrentSession: () => {
        set({ currentSession: null })
      },
      
      // 保存分析结果（用于并行/快速分析模式）
      saveAnalysisResult: (result) => {
        set(state => {
          if (!state.currentSession) return state
          
          const updatedSession = {
            ...state.currentSession,
            analysisResult: result,
            updatedAt: new Date()
          }
          
          const stockCode = updatedSession.stockCode
          const updatedSessions = (state.sessions[stockCode] || []).map(s =>
            s.id === updatedSession.id ? updatedSession : s
          )
          
          return {
            currentSession: updatedSession,
            sessions: {
              ...state.sessions,
              [stockCode]: updatedSessions
            }
          }
        })
      },
      
      // 更新会话状态
      updateSessionStatus: (status) => {
        set(state => {
          if (!state.currentSession) return state
          
          const updatedSession = {
            ...state.currentSession,
            status,
            updatedAt: new Date()
          }
          
          const stockCode = updatedSession.stockCode
          const updatedSessions = (state.sessions[stockCode] || []).map(s =>
            s.id === updatedSession.id ? updatedSession : s
          )
          
          return {
            currentSession: updatedSession,
            sessions: {
              ...state.sessions,
              [stockCode]: updatedSessions
            }
          }
        })
      },
      
      // 恢复会话
      restoreSession: (sessionId) => {
        const state = get()
        for (const stockCode of Object.keys(state.sessions)) {
          const session = state.sessions[stockCode].find(s => s.id === sessionId)
          if (session) {
            set({ currentSession: session })
            return session
          }
        }
        return null
      },
      
      // 获取最近未完成的会话
      getLatestInProgressSession: (stockCode) => {
        const state = get()
        const stockSessions = state.sessions[stockCode] || []
        return stockSessions.find(s => s.status === 'in_progress') || null
      },
      
      loadSession: (stockCode, sessionId) => {
        const state = get()
        const stockSessions = state.sessions[stockCode] || []
        
        if (sessionId) {
          const session = stockSessions.find(s => s.id === sessionId)
          if (session) {
            set({ currentSession: session })
            return session
          }
        }
        
        // 如果没有指定 sessionId，返回最新的会话
        if (stockSessions.length > 0) {
          const latestSession = stockSessions[0]
          set({ currentSession: latestSession })
          return latestSession
        }
        
        return null
      },
      
      getStockSessions: (stockCode) => {
        return get().sessions[stockCode] || []
      },
      
      deleteSession: (stockCode, sessionId) => {
        set(state => {
          const updatedSessions = (state.sessions[stockCode] || []).filter(
            s => s.id !== sessionId
          )
          
          return {
            sessions: {
              ...state.sessions,
              [stockCode]: updatedSessions
            },
            // 如果删除的是当前会话，清空当前会话
            currentSession: state.currentSession?.id === sessionId 
              ? null 
              : state.currentSession
          }
        })
      },
      
      clearStockHistory: async (stockCode) => {
        // 1. 先清除本地 Store
        set(state => {
          const { [stockCode]: _, ...rest } = state.sessions
          return {
            sessions: rest,
            currentSession: state.currentSession?.stockCode === stockCode
              ? null
              : state.currentSession
          }
        })
        
        // 2. 同时清除后端数据库中的历史
        try {
          const response = await fetch(`/api/v1/agents/debate/history/${stockCode}`, {
            method: 'DELETE'
          })
          if (response.ok) {
            console.log('✅ 已清除后端历史记录')
          } else {
            console.error('❌ 清除后端历史失败')
          }
        } catch (error) {
          console.error('❌ 清除后端历史出错:', error)
        }
      },
      
      // 同步到后端
      syncToBackend: async (stockCode) => {
        const state = get()
        const sessions = state.sessions[stockCode]
        
        console.log('💾 syncToBackend called for:', stockCode)
        console.log('💾 Sessions count:', sessions?.length || 0)
        
        if (!sessions || sessions.length === 0) {
          console.warn('⚠️ syncToBackend: no sessions to sync')
          return
        }
        
        // 打印每个会话的消息数量
        sessions.forEach((s, i) => {
          console.log(`💾 Session ${i}: ${s.id}, messages: ${s.messages.length}`)
          console.log(`💾 Session ${i} roles:`, s.messages.map(m => m.role))
        })
        
        try {
          const serialized = sessions.map(serializeSession)
          console.log('💾 Sending to backend:', JSON.stringify(serialized).slice(0, 500) + '...')
          
          const response = await fetch(`/api/v1/agents/debate/history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              stock_code: stockCode,
              sessions: serialized
            })
          })
          
          if (!response.ok) {
            console.error('Failed to sync debate history to backend')
          } else {
            console.log('✅ Synced to backend successfully')
          }
        } catch (error) {
          console.error('Error syncing debate history:', error)
        }
      },
      
      // 从后端加载
      loadFromBackend: async (stockCode) => {
        console.log('📥 loadFromBackend called for:', stockCode)
        
        try {
          const response = await fetch(`/api/v1/agents/debate/history/${stockCode}`)
          
          if (response.ok) {
            const data = await response.json()
            console.log('📥 Loaded from backend:', data)
            
            if (data.sessions && data.sessions.length > 0) {
              const sessions = data.sessions.map(deserializeSession)
              console.log('📥 Deserialized sessions:', sessions.length)
              sessions.forEach((s: any, i: number) => {
                console.log(`📥 Session ${i}: ${s.id}, messages: ${s.messages.length}`)
                console.log(`📥 Session ${i} roles:`, s.messages.map((m: any) => m.role))
              })
              
              set(state => ({
                sessions: {
                  ...state.sessions,
                  [stockCode]: sessions
                }
              }))
            } else {
              console.log('📥 No sessions in response')
            }
          } else {
            console.error('📥 Failed to load:', response.status)
          }
        } catch (error) {
          console.error('Error loading debate history from backend:', error)
        }
      }
    }),
    {
      name: 'finnews-debate-history',
      // 自定义序列化
      serialize: (state) => {
        const serialized = {
          ...state,
          state: {
            ...state.state,
            currentSession: state.state.currentSession 
              ? serializeSession(state.state.currentSession)
              : null,
            sessions: Object.fromEntries(
              Object.entries(state.state.sessions).map(([k, v]) => [
                k,
                (v as DebateSession[]).map(serializeSession)
              ])
            )
          }
        }
        return JSON.stringify(serialized)
      },
      // 自定义反序列化
      deserialize: (str) => {
        const parsed = JSON.parse(str)
        return {
          ...parsed,
          state: {
            ...parsed.state,
            currentSession: parsed.state.currentSession
              ? deserializeSession(parsed.state.currentSession)
              : null,
            sessions: Object.fromEntries(
              Object.entries(parsed.state.sessions).map(([k, v]) => [
                k,
                (v as SerializedSession[]).map(deserializeSession)
              ])
            )
          }
        }
      }
    }
  )
)

