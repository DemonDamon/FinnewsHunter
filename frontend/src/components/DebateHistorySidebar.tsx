import React, { useState, useMemo } from 'react'
import { 
  History, 
  Trash2, 
  MessageSquare, 
  Clock, 
  PlayCircle,
  Swords,
  Zap,
  Activity,
  X,
  Search,
  Calendar
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { DebateSession } from '@/store/useDebateStore'
import { useGlobalI18n } from '@/store/useLanguageStore'

interface DebateHistorySidebarProps {
  sessions: DebateSession[]
  currentSessionId?: string | null
  onLoadSession: (session: DebateSession) => void
  onDeleteSession?: (sessionId: string) => void
  onClearHistory?: () => void
  isOpen: boolean
  onToggle: () => void
}

// 获取模式图标和样式（支持国际化）
const getModeInfo = (mode: string, t: any) => {
  switch (mode) {
    case 'parallel':
      return {
        icon: <Zap className="w-3.5 h-3.5" />,
        label: t.stockDetail.parallelAnalysis,
        color: 'text-amber-600',
        bgColor: 'bg-amber-50'
      }
    case 'realtime_debate':
      return {
        icon: <Swords className="w-3.5 h-3.5" />,
        label: t.stockDetail.realtimeDebate,
        color: 'text-purple-600',
        bgColor: 'bg-purple-50'
      }
    case 'quick_analysis':
      return {
        icon: <Activity className="w-3.5 h-3.5" />,
        label: t.stockDetail.quickAnalysis || 'Quick Analysis',
        color: 'text-blue-600',
        bgColor: 'bg-blue-50'
      }
    default:
      return {
        icon: <MessageSquare className="w-3.5 h-3.5" />,
        label: t.stockDetail.bullBear || 'Debate',
        color: 'text-gray-600',
        bgColor: 'bg-gray-50'
      }
  }
}

// 格式化时间（支持国际化）
const formatTime = (date: Date, t: any) => {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return t.debateHistory.justNow
  if (minutes < 60) return `${minutes}${t.debateHistory.minutesAgo}`
  if (hours < 24) return `${hours}${t.debateHistory.hoursAgo}`
  if (days < 7) return `${days}${t.debateHistory.daysAgo}`
  
  return date.toLocaleDateString(t.debateHistory.justNow === '刚刚' ? 'zh-CN' : 'en-US', {
    month: 'short',
    day: 'numeric'
  })
}

// 会话预览内容（支持国际化）
const getSessionPreview = (session: DebateSession, t: any) => {
  if (session.messages.length === 0) {
    return t.debateHistory.noMessages
  }
  
  // 获取最后一条非系统消息
  const lastMessage = [...session.messages]
    .reverse()
    .find(m => m.role !== 'system')
  
  if (lastMessage) {
    const roleName = t.debateHistory.roleNames[lastMessage.role] || lastMessage.role
    const content = lastMessage.content.slice(0, 40)
    return `${roleName}: ${content}${lastMessage.content.length > 40 ? '...' : ''}`
  }
  
  return `${session.messages.length} ${t.debateHistory.messages}`
}

const DebateHistorySidebar: React.FC<DebateHistorySidebarProps> = ({
  sessions,
  currentSessionId,
  onLoadSession,
  onDeleteSession,
  onClearHistory,
  isOpen,
  onToggle
}) => {
  const t = useGlobalI18n()
  const [searchTerm, setSearchTerm] = useState('')
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  // 过滤会话
  const filteredSessions = useMemo(() => {
    if (!searchTerm) return sessions
    const term = searchTerm.toLowerCase()
    return sessions.filter(s => 
      s.stockName?.toLowerCase().includes(term) ||
      s.messages.some(m => m.content.toLowerCase().includes(term))
    )
  }, [sessions, searchTerm])

  // 按日期分组
  const groupedSessions = useMemo(() => {
    const groups: { label: string; sessions: DebateSession[] }[] = []
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    const weekAgo = new Date(today)
    weekAgo.setDate(weekAgo.getDate() - 7)

    const todaySessions: DebateSession[] = []
    const yesterdaySessions: DebateSession[] = []
    const thisWeekSessions: DebateSession[] = []
    const olderSessions: DebateSession[] = []

    filteredSessions.forEach(session => {
      const sessionDate = new Date(session.updatedAt)
      sessionDate.setHours(0, 0, 0, 0)

      if (sessionDate.getTime() === today.getTime()) {
        todaySessions.push(session)
      } else if (sessionDate.getTime() === yesterday.getTime()) {
        yesterdaySessions.push(session)
      } else if (sessionDate > weekAgo) {
        thisWeekSessions.push(session)
      } else {
        olderSessions.push(session)
      }
    })

    if (todaySessions.length > 0) groups.push({ label: t.debateHistory.today, sessions: todaySessions })
    if (yesterdaySessions.length > 0) groups.push({ label: t.debateHistory.yesterday, sessions: yesterdaySessions })
    if (thisWeekSessions.length > 0) groups.push({ label: t.debateHistory.thisWeek, sessions: thisWeekSessions })
    if (olderSessions.length > 0) groups.push({ label: t.debateHistory.older, sessions: olderSessions })

    return groups
  }, [filteredSessions, t])

  return (
    <>
      {/* 折叠状态的标签按钮 */}
      {!isOpen && sessions.length > 0 && (
        <button
          onClick={onToggle}
          className="fixed right-0 top-1/2 -translate-y-1/2 z-40 bg-white shadow-lg rounded-l-lg px-2 py-4 border border-r-0 border-gray-200 hover:bg-gray-50 transition-colors group"
          title={t.debateHistory.expandHistory}
        >
          <div className="flex flex-col items-center gap-2">
            <History className="w-5 h-5 text-gray-600 group-hover:text-indigo-600" />
            <span className="text-xs font-medium text-gray-600 writing-vertical group-hover:text-indigo-600">
              {t.debateHistory.history}
            </span>
            <span className="text-xs bg-indigo-100 text-indigo-600 rounded-full w-5 h-5 flex items-center justify-center">
              {sessions.length}
            </span>
          </div>
        </button>
      )}

      {/* 侧边栏面板 */}
      <div
        className={cn(
          "fixed right-0 top-0 h-full bg-white shadow-2xl border-l border-gray-200 z-50 transition-transform duration-300 ease-in-out flex flex-col",
          isOpen ? "translate-x-0" : "translate-x-full",
          "w-80"
        )}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-indigo-50 to-purple-50">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center">
              <History className="w-4 h-4 text-indigo-600" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">{t.debateHistory.history}</h3>
              <p className="text-xs text-gray-500">{sessions.length} {t.stockDetail.session}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggle}
            className="h-8 w-8 text-gray-500 hover:text-gray-700"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* 搜索框 */}
        <div className="px-3 py-2 border-b border-gray-100">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={t.debateHistory.searchPlaceholder}
              className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-300"
            />
          </div>
        </div>

        {/* 会话列表 */}
        <div className="flex-1 overflow-y-auto">
          {groupedSessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 px-4">
              <History className="w-12 h-12 mb-3 opacity-50" />
              <p className="text-sm text-center">
                {searchTerm ? t.debateHistory.noMatchingRecords : t.debateHistory.noHistoryYet}
              </p>
              <p className="text-xs mt-1 text-center">
                {searchTerm ? t.debateHistory.tryOtherKeywords : t.debateHistory.historyAutoSave}
              </p>
            </div>
          ) : (
            <div className="py-2">
              {groupedSessions.map(group => (
                <div key={group.label} className="mb-4">
                  <div className="px-4 py-1.5 text-xs font-medium text-gray-500 uppercase tracking-wider flex items-center gap-2">
                    <Calendar className="w-3 h-3" />
                    {group.label}
                  </div>
                  {group.sessions.map(session => {
                    const modeInfo = getModeInfo(session.mode, t)
                    const isActive = session.id === currentSessionId
                    const isHovered = session.id === hoveredId
                    
                    return (
                      <div
                        key={session.id}
                        className={cn(
                          "relative px-3 py-2 mx-2 rounded-lg cursor-pointer transition-all duration-200",
                          isActive 
                            ? "bg-indigo-50 border border-indigo-200" 
                            : "hover:bg-gray-50 border border-transparent"
                        )}
                        onMouseEnter={() => setHoveredId(session.id)}
                        onMouseLeave={() => setHoveredId(null)}
                        onClick={() => onLoadSession(session)}
                      >
                        <div className="flex items-start gap-3">
                          {/* 模式图标 */}
                          <div className={cn(
                            "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5",
                            modeInfo.bgColor,
                            modeInfo.color
                          )}>
                            {modeInfo.icon}
                          </div>
                          
                          {/* 会话信息 */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={cn(
                                "text-sm font-medium truncate",
                                isActive ? "text-indigo-700" : "text-gray-700"
                              )}>
                                {session.stockName || session.stockCode}
                              </span>
                              <span className={cn(
                                "text-[10px] px-1.5 py-0.5 rounded",
                                modeInfo.bgColor,
                                modeInfo.color
                              )}>
                                {modeInfo.label}
                              </span>
                            </div>
                            
                            <p className="text-xs text-gray-500 mt-0.5 truncate">
                              {getSessionPreview(session, t)}
                            </p>
                            
                            <div className="flex items-center gap-2 mt-1.5 text-[10px] text-gray-400">
                              <span className="flex items-center gap-1">
                                <MessageSquare className="w-3 h-3" />
                                {session.messages.length}
                              </span>
                              <span>·</span>
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {formatTime(new Date(session.updatedAt), t)}
                              </span>
                            </div>
                          </div>
                          
                          {/* 操作按钮 */}
                          <div className={cn(
                            "flex items-center gap-1 transition-opacity",
                            isHovered || isActive ? "opacity-100" : "opacity-0"
                          )}>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-indigo-500 hover:text-indigo-600 hover:bg-indigo-100"
                              onClick={(e) => {
                                e.stopPropagation()
                                onLoadSession(session)
                              }}
                              title={t.debateHistory.continueDebate}
                            >
                              <PlayCircle className="w-3.5 h-3.5" />
                            </Button>
                            {onDeleteSession && (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-rose-400 hover:text-rose-500 hover:bg-rose-50"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  if (confirm(t.stockDetail.deleteSessionConfirm)) {
                                    onDeleteSession(session.id)
                                  }
                                }}
                                title={t.debateHistory.delete}
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </Button>
                            )}
                          </div>
                        </div>
                        
                        {/* 活跃指示器 */}
                        {isActive && (
                          <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-indigo-500 rounded-r" />
                        )}
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 底部操作 */}
        {sessions.length > 0 && onClearHistory && (
          <div className="px-4 py-3 border-t border-gray-100 bg-gray-50">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (confirm(t.stockDetail.clearAllHistoryConfirm)) {
                  onClearHistory()
                }
              }}
              className="w-full text-rose-500 border-rose-200 hover:bg-rose-50 hover:text-rose-600"
            >
              <Trash2 className="w-3.5 h-3.5 mr-2" />
              {t.stockDetail.clearAllRecords}
            </Button>
          </div>
        )}
      </div>

      {/* 遮罩层 */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40 transition-opacity"
          onClick={onToggle}
        />
      )}
    </>
  )
}

export default DebateHistorySidebar

