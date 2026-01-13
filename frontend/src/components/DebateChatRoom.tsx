import React, { useState, useRef, useEffect, useCallback } from 'react'
import { 
  Send, User, TrendingUp, TrendingDown, Briefcase, 
  Loader2, Bot, History, Trash2, Search, ChevronDown,
  CheckCircle2, Clock, ListChecks, PlayCircle, XCircle
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'
import MentionInput, { MentionTarget } from './MentionInput'
import type { DebateSession } from '@/store/useDebateStore'
import { agentApi, SSEDebateEvent } from '@/lib/api-client'
import { toast } from 'sonner'
import { useGlobalI18n, useLanguageStore } from '@/store/useLanguageStore'

// 消息角色类型
export type ChatRole = 'user' | 'bull' | 'bear' | 'manager' | 'system' | 'data_collector' | 'search'

// 搜索计划类型
export interface SearchTask {
  id: string
  source: string
  query: string
  description: string
  icon: string
  estimated_time: number
}

export interface SearchPlan {
  plan_id: string
  stock_code: string
  stock_name: string
  user_query: string
  tasks: SearchTask[]
  total_estimated_time: number
}

// 聊天消息类型
export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  timestamp: Date
  round?: number
  isStreaming?: boolean
  searchPlan?: SearchPlan // 关联的搜索计划
  searchStatus?: 'pending' | 'executing' | 'completed' | 'cancelled'
}

// 获取角色配置（支持国际化）
const getRoleConfig = (t: any): Record<ChatRole, {
  name: string
  icon: React.ReactNode
  bgColor: string
  textColor: string
  borderColor: string
  align: 'left' | 'right'
}> => ({
  user: {
    name: t.debateHistory.roleNames.user,
    icon: <User className="w-4 h-4" />,
    bgColor: 'bg-blue-500',
    textColor: 'text-white',
    borderColor: 'border-blue-500',
    align: 'right'
  },
  bull: {
    name: t.debateHistory.roleNames.bull,
    icon: <TrendingUp className="w-4 h-4" />,
    bgColor: 'bg-emerald-500',
    textColor: 'text-white',
    borderColor: 'border-emerald-300',
    align: 'left'
  },
  bear: {
    name: t.debateHistory.roleNames.bear,
    icon: <TrendingDown className="w-4 h-4" />,
    bgColor: 'bg-rose-500',
    textColor: 'text-white',
    borderColor: 'border-rose-300',
    align: 'left'
  },
  manager: {
    name: t.debateHistory.roleNames.manager,
    icon: <Briefcase className="w-4 h-4" />,
    bgColor: 'bg-indigo-500',
    textColor: 'text-white',
    borderColor: 'border-indigo-300',
    align: 'left'
  },
  data_collector: {
    name: t.debateHistory.roleNames.data_collector,
    icon: <Bot className="w-4 h-4" />,
    bgColor: 'bg-purple-500',
    textColor: 'text-white',
    borderColor: 'border-purple-300',
    align: 'left'
  },
  system: {
    name: 'System',
    icon: <Bot className="w-4 h-4" />,
    bgColor: 'bg-gray-400',
    textColor: 'text-white',
    borderColor: 'border-gray-200',
    align: 'left'
  },
  search: {
    name: 'Search Results',
    icon: <Bot className="w-4 h-4" />,
    bgColor: 'bg-cyan-500',
    textColor: 'text-white',
    borderColor: 'border-cyan-300',
    align: 'left'
  }
})

interface DebateChatRoomProps {
  messages: ChatMessage[]
  onSendMessage: (content: string, mentions?: MentionTarget[]) => void
  isDebating: boolean
  currentRound?: { round: number; maxRounds: number } | null
  activeAgent?: string | null
  stockName?: string
  disabled?: boolean
  // 历史相关
  historySessions?: DebateSession[]
  onLoadSession?: (sessionId: string) => void
  onClearHistory?: () => void
  showHistory?: boolean
  // 搜索计划相关
  onConfirmSearch?: (plan: SearchPlan, msgId: string) => void
  onCancelSearch?: (msgId: string) => void
}

// 搜索计划展示组件
const SearchPlanCard: React.FC<{ 
  plan: SearchPlan, 
  status: string,
  onConfirm: (plan: SearchPlan) => void,
  onCancel: () => void
}> = ({ plan, status, onConfirm, onCancel }) => {
  const t = useGlobalI18n()
  const isPending = status === 'pending'
  const isExecuting = status === 'executing'
  
  return (
    <div className="mt-3 p-4 bg-slate-50 rounded-xl border border-slate-200 shadow-sm animate-in fade-in zoom-in duration-300">
      <div className="flex items-center gap-2 mb-3 pb-2 border-b border-slate-200">
        <ListChecks className="w-5 h-5 text-indigo-500" />
        <h4 className="font-semibold text-slate-800 text-sm">📋 {t.debateRoom.searchPlanConfirm}</h4>
      </div>
      
      <div className="space-y-2 mb-4">
        {plan.tasks.map((task, index) => (
          <div key={task.id} className="flex items-start gap-3 text-xs text-slate-600">
            <span className="mt-0.5">{task.icon || '🔍'}</span>
            <div className="flex-1">
              <p className="font-medium text-slate-700">{index + 1}. {task.description}</p>
              <p className="text-[10px] text-slate-400">{t.debateRoom.roundPrefix === '第' ? '关键词' : 'Keyword'}: "{task.query}"</p>
            </div>
          </div>
        ))}
      </div>
      
      <div className="flex items-center justify-between pt-2">
        <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
          <Clock className="w-3 h-3" />
          {t.debateRoom.estimatedTime}: {plan.total_estimated_time}{t.debateRoom.seconds}
        </div>
        
        {isPending && (
          <div className="flex gap-2">
            <Button 
              size="sm" 
              variant="outline" 
              className="h-7 text-[10px] px-3 py-0"
              onClick={onCancel}
            >
              {t.debateRoom.searchPlanCancel}
            </Button>
            <Button 
              size="sm" 
              className="h-7 text-[10px] px-3 py-0 bg-indigo-500 hover:bg-indigo-600"
              onClick={() => onConfirm(plan)}
            >
              {t.debateRoom.searchPlanConfirmBtn}
            </Button>
          </div>
        )}
        
        {isExecuting && (
          <div className="flex items-center gap-2 text-[10px] text-indigo-600 animate-pulse">
            <Loader2 className="w-3 h-3 animate-spin" />
            {t.debateRoom.searchPlanExecuting}
          </div>
        )}
        
        {status === 'completed' && (
          <div className="flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
            <CheckCircle2 className="w-3 h-3" />
            {t.debateRoom.searchPlanCompleted}
          </div>
        )}
      </div>
    </div>
  )
}

// 单条消息组件
const ChatBubble: React.FC<{ 
  message: ChatMessage,
  onConfirmSearch?: (plan: SearchPlan, msgId: string) => void,
  onCancelSearch?: (msgId: string) => void
}> = ({ message, onConfirmSearch, onCancelSearch }) => {
  const t = useGlobalI18n()
  const ROLE_CONFIG = getRoleConfig(t)
  const config = ROLE_CONFIG[message.role]
  const isRight = config.align === 'right'
  
  return (
    <div className={cn(
      "flex gap-2 mb-4 animate-in fade-in slide-in-from-bottom-2 duration-300",
      isRight ? "flex-row-reverse" : "flex-row"
    )}>
      {/* 头像 */}
      <div className={cn(
        "w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm",
        config.bgColor,
        config.textColor
      )}>
        {config.icon}
      </div>
      
      {/* 消息体 */}
      <div className={cn("flex flex-col max-w-[75%]", isRight ? "items-end" : "items-start")}>
        {/* 角色名称和轮次 */}
        <div className={cn(
          "flex items-center gap-2 mb-1 text-xs",
          isRight ? "flex-row-reverse" : "flex-row"
        )}>
          <span className="font-medium text-gray-600">{config.name}</span>
          {message.round && (
            <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 text-[10px]">
              {t.debateRoom.roundPrefix}{message.round}{t.debateRoom.roundSuffix}
            </span>
          )}
          <span className="text-gray-400">
            {message.timestamp.toLocaleTimeString(t.debateRoom.roundPrefix === '第' ? 'zh-CN' : 'en-US', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        
        {/* 消息气泡 */}
        <div className={cn(
          "rounded-2xl px-4 py-2.5 shadow-sm border",
          isRight 
            ? "bg-blue-500 text-white rounded-tr-sm border-blue-400" 
            : `bg-white ${config.borderColor} rounded-tl-sm`
        )}>
          {message.content ? (
            <div className={cn(
              "prose prose-sm max-w-none",
              isRight ? "prose-invert" : "prose-gray"
            )}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
              {message.isStreaming && (
                <span className="inline-block w-2 h-4 bg-current opacity-70 animate-pulse ml-1 align-middle rounded-sm" />
              )}
            </div>
          ) : message.searchPlan ? (
            <div className="text-sm text-gray-500 italic">{t.stockDetail.generatingSearchPlan}</div>
          ) : (
            <div className="flex items-center gap-2 text-gray-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">{t.debateRoom.thinking}</span>
            </div>
          )}
          
          {/* 搜索计划卡片 */}
          {message.searchPlan && (
            <SearchPlanCard 
              plan={message.searchPlan} 
              status={message.searchStatus || 'pending'}
              onConfirm={(plan) => onConfirmSearch?.(plan, message.id)}
              onCancel={() => onCancelSearch?.(message.id)}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// 系统消息组件
const SystemMessage: React.FC<{ message: ChatMessage }> = ({ message }) => (
  <div className="flex justify-center my-3">
    <div className="px-3 py-1 rounded-full bg-gray-100 text-gray-500 text-xs">
      {message.content}
    </div>
  </div>
)

// 主组件
const DebateChatRoom: React.FC<DebateChatRoomProps> = ({
  messages,
  onSendMessage,
  isDebating,
  currentRound,
  activeAgent,
  stockName,
  disabled = false,
  historySessions = [],
  onLoadSession,
  onClearHistory,
  showHistory = true,
  onConfirmSearch,
  onCancelSearch
}) => {
  const t = useGlobalI18n()
  const ROLE_CONFIG = getRoleConfig(t)
  const [inputValue, setInputValue] = useState('')
  const [showHistoryDropdown, setShowHistoryDropdown] = useState(false)
  const [pendingMentions, setPendingMentions] = useState<MentionTarget[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const historyDropdownRef = useRef<HTMLDivElement>(null)
  
  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])
  
  // 点击外部关闭历史下拉框
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (historyDropdownRef.current && !historyDropdownRef.current.contains(e.target as Node)) {
        setShowHistoryDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])
  
  const handleSendWithMentions = useCallback((content: string, mentions: MentionTarget[]) => {
    if (content.trim() && !disabled && !isDebating) {
      onSendMessage(content.trim(), mentions)
      setInputValue('')
      setPendingMentions([])
    }
  }, [disabled, isDebating, onSendMessage])
  
  // 获取当前活跃角色的提示
  const getActiveIndicator = () => {
    if (!activeAgent) return null
    
    const agentMap: Record<string, ChatRole> = {
      'BullResearcher': 'bull',
      'BearResearcher': 'bear',
      'InvestmentManager': 'manager',
      'DataCollector': 'data_collector'
    }
    
    const role = agentMap[activeAgent]
    if (!role) return null
    
    const config = ROLE_CONFIG[role]
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <div className={cn("w-2 h-2 rounded-full animate-pulse", config.bgColor)} />
        <span>{config.name} {t.debateRoom.typing}</span>
      </div>
    )
  }
  
  return (
    <div className="flex flex-col h-[600px] bg-gradient-to-b from-gray-50 to-white rounded-xl border shadow-lg overflow-hidden">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 bg-white border-b">
        <div className="flex items-center gap-3">
          <div className="flex -space-x-2">
            <div className="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center text-white ring-2 ring-white">
              <TrendingUp className="w-4 h-4" />
            </div>
            <div className="w-8 h-8 rounded-full bg-rose-500 flex items-center justify-center text-white ring-2 ring-white">
              <TrendingDown className="w-4 h-4" />
            </div>
            <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center text-white ring-2 ring-white">
              <Briefcase className="w-4 h-4" />
            </div>
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">
              {stockName ? `${stockName} ${t.debateRoom.title}` : t.debateRoom.titlePlaceholder}
            </h3>
            <p className="text-xs text-gray-500">{t.debateRoom.subtitle}</p>
          </div>
        </div>
        
        {/* 轮次指示器 */}
        {currentRound && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-purple-50 rounded-full">
            <div className="flex gap-0.5">
              {Array.from({ length: currentRound.maxRounds }, (_, i) => (
                <div
                  key={i}
                  className={cn(
                    "w-2 h-2 rounded-full transition-colors",
                    i < currentRound.round
                      ? 'bg-purple-500'
                      : 'bg-gray-200'
                  )}
                />
              ))}
            </div>
            <span className="text-xs font-medium text-purple-600">
              {t.debateRoom.roundPrefix}{currentRound.round}{t.debateRoom.roundSuffix}
            </span>
          </div>
        )}
      </div>
      
      {/* 消息区域 */}
      <div 
        ref={scrollRef}
        className="flex-1 px-4 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent"
      >
        <div className="py-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 py-20">
              <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mb-4">
                <Briefcase className="w-8 h-8 text-gray-300" />
              </div>
              <p className="text-sm mb-2">{t.debateRoom.clickStartDebate}</p>
              <p className="text-xs">{t.debateRoom.canSpeakDuringDebate}</p>
            </div>
          ) : (
            messages.map((msg) => (
              msg.role === 'system' ? (
                <SystemMessage key={msg.id} message={msg} />
              ) : (
                <ChatBubble 
                  key={msg.id} 
                  message={msg} 
                  onConfirmSearch={onConfirmSearch}
                  onCancelSearch={onCancelSearch}
                />
              )
            ))
          )}
          
          {/* 输入指示器 */}
          {isDebating && activeAgent && (
            <div className="flex items-center gap-2 ml-11 mb-4">
              {getActiveIndicator()}
            </div>
          )}
        </div>
      </div>
      
      {/* 输入区域 */}
      <div className="px-4 py-3 bg-white border-t">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white flex-shrink-0">
            <User className="w-4 h-4" />
          </div>
          <MentionInput
            value={inputValue}
            onChange={setInputValue}
            onSubmit={handleSendWithMentions}
            placeholder={isDebating ? t.debateRoom.debateInProgress : t.mentionInput.placeholder}
            disabled={disabled}
          />
          <Button
            onClick={() => handleSendWithMentions(inputValue, pendingMentions)}
            disabled={!inputValue.trim() || disabled || isDebating}
            size="icon"
            className="rounded-full bg-blue-500 hover:bg-blue-600"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
        
        {/* 提示和历史按钮 */}
        <div className="flex items-center justify-between mt-2 ml-10">
          {isDebating ? (
            <p className="text-xs text-gray-400">
              💡 {t.debateRoom.mentionTip}
            </p>
          ) : (
            <p className="text-xs text-gray-400">
              💡 {t.stockDetail.history === '历史' ? '输入 @ 可以选择智能体或数据源' : 'Enter @ to select agents or data sources'}
          </p>
        )}
          
          {/* 历史记录按钮 */}
          {showHistory && historySessions.length > 0 && (
            <div className="relative" ref={historyDropdownRef}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowHistoryDropdown(!showHistoryDropdown)}
                className="h-7 px-2 text-gray-500 hover:text-gray-700"
              >
                <History className="w-3.5 h-3.5 mr-1" />
                {t.debateHistory.history} ({historySessions.length})
                <ChevronDown className={cn("w-3 h-3 ml-1 transition-transform", showHistoryDropdown && "rotate-180")} />
              </Button>
              
              {/* 历史下拉菜单 */}
              {showHistoryDropdown && (
                <div className="absolute bottom-full right-0 mb-1 w-64 bg-white rounded-lg shadow-xl border border-gray-200 py-2 z-50 animate-in fade-in slide-in-from-bottom-2 duration-200">
                  <div className="px-3 py-1 border-b border-gray-100 flex items-center justify-between">
                    <span className="text-xs font-medium text-gray-500">{t.debateHistory.history} {t.stockDetail.session}</span>
                    {onClearHistory && (
                      <button 
                        onClick={() => {
                          if (confirm(t.agents.confirmClearLogs)) {
                            onClearHistory()
                            setShowHistoryDropdown(false)
                          }
                        }}
                        className="text-xs text-rose-500 hover:text-rose-600 flex items-center gap-1"
                      >
                        <Trash2 className="w-3 h-3" />
                        {t.common.cancel === '取消' ? '清除' : 'Clear'}
                      </button>
                    )}
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {historySessions.map((session, index) => (
                      <button
                        key={session.id}
                        onClick={() => {
                          onLoadSession?.(session.id)
                          setShowHistoryDropdown(false)
                        }}
                        className="w-full px-3 py-2 text-left hover:bg-gray-50 flex items-center gap-2"
                      >
                        <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs text-gray-500 flex-shrink-0">
                          {index + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gray-700 truncate">
                            {session.stockName || session.stockCode}
                          </div>
                          <div className="text-xs text-gray-400">
                            {session.messages.length} {t.debateHistory.messages} · {new Date(session.updatedAt).toLocaleDateString(t.debateRoom.roundPrefix === '第' ? 'zh-CN' : 'en-US')}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default DebateChatRoom

