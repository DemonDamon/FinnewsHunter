import React, { useState, useRef, useEffect } from 'react'
import { Send, User, TrendingUp, TrendingDown, Briefcase, Loader2, Bot } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

// 消息角色类型
export type ChatRole = 'user' | 'bull' | 'bear' | 'manager' | 'system' | 'data_collector'

// 聊天消息类型
export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  timestamp: Date
  round?: number
  isStreaming?: boolean
}

// 角色配置
const ROLE_CONFIG: Record<ChatRole, {
  name: string
  icon: React.ReactNode
  bgColor: string
  textColor: string
  borderColor: string
  align: 'left' | 'right'
}> = {
  user: {
    name: '我',
    icon: <User className="w-4 h-4" />,
    bgColor: 'bg-blue-500',
    textColor: 'text-white',
    borderColor: 'border-blue-500',
    align: 'right'
  },
  bull: {
    name: '多方辩手',
    icon: <TrendingUp className="w-4 h-4" />,
    bgColor: 'bg-emerald-500',
    textColor: 'text-white',
    borderColor: 'border-emerald-300',
    align: 'left'
  },
  bear: {
    name: '空方辩手',
    icon: <TrendingDown className="w-4 h-4" />,
    bgColor: 'bg-rose-500',
    textColor: 'text-white',
    borderColor: 'border-rose-300',
    align: 'left'
  },
  manager: {
    name: '投资经理',
    icon: <Briefcase className="w-4 h-4" />,
    bgColor: 'bg-indigo-500',
    textColor: 'text-white',
    borderColor: 'border-indigo-300',
    align: 'left'
  },
  data_collector: {
    name: '数据专员',
    icon: <Bot className="w-4 h-4" />,
    bgColor: 'bg-purple-500',
    textColor: 'text-white',
    borderColor: 'border-purple-300',
    align: 'left'
  },
  system: {
    name: '系统',
    icon: <Bot className="w-4 h-4" />,
    bgColor: 'bg-gray-400',
    textColor: 'text-white',
    borderColor: 'border-gray-200',
    align: 'left'
  }
}

interface DebateChatRoomProps {
  messages: ChatMessage[]
  onSendMessage: (content: string) => void
  isDebating: boolean
  currentRound?: { round: number; maxRounds: number } | null
  activeAgent?: string | null
  stockName?: string
  disabled?: boolean
}

// 单条消息组件
const ChatBubble: React.FC<{ message: ChatMessage }> = ({ message }) => {
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
              第{message.round}轮
            </span>
          )}
          <span className="text-gray-400">
            {message.timestamp.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        
        {/* 消息气泡 */}
        <div className={cn(
          "rounded-2xl px-4 py-2.5 shadow-sm border",
          isRight 
            ? "bg-blue-500 text-white rounded-tr-sm border-blue-400" 
            : `bg-white ${config.borderColor} rounded-tl-sm`,
          message.isStreaming && "animate-pulse"
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
                <span className="inline-block w-1.5 h-4 bg-current animate-pulse ml-0.5 align-middle" />
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-gray-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">思考中...</span>
            </div>
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
  disabled = false
}) => {
  const [inputValue, setInputValue] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  
  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      const scrollElement = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]')
      if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight
      }
    }
  }, [messages])
  
  const handleSend = () => {
    if (inputValue.trim() && !disabled && !isDebating) {
      onSendMessage(inputValue.trim())
      setInputValue('')
      inputRef.current?.focus()
    }
  }
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }
  
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
        <span>{config.name} 正在输入...</span>
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
              {stockName ? `${stockName} 投资辩论` : '多空辩论室'}
            </h3>
            <p className="text-xs text-gray-500">多方 vs 空方 · 投资经理主持</p>
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
              第{currentRound.round}轮
            </span>
          </div>
        )}
      </div>
      
      {/* 消息区域 */}
      <ScrollArea className="flex-1 px-4" ref={scrollRef}>
        <div className="py-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 py-20">
              <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mb-4">
                <Briefcase className="w-8 h-8 text-gray-300" />
              </div>
              <p className="text-sm">点击「开始辩论」启动多空对决</p>
              <p className="text-xs mt-1">您也可以在辩论过程中发言提问</p>
            </div>
          ) : (
            messages.map((msg) => (
              msg.role === 'system' ? (
                <SystemMessage key={msg.id} message={msg} />
              ) : (
                <ChatBubble key={msg.id} message={msg} />
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
      </ScrollArea>
      
      {/* 输入区域 */}
      <div className="px-4 py-3 bg-white border-t">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white flex-shrink-0">
            <User className="w-4 h-4" />
          </div>
          <Input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isDebating ? "辩论进行中，您可以提问或评论..." : "输入消息参与辩论..."}
            disabled={disabled}
            className="flex-1 rounded-full bg-gray-50 border-gray-200 focus:border-blue-300"
          />
          <Button
            onClick={handleSend}
            disabled={!inputValue.trim() || disabled || isDebating}
            size="icon"
            className="rounded-full bg-blue-500 hover:bg-blue-600"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
        {isDebating && (
          <p className="text-xs text-gray-400 mt-2 ml-10">
            💡 提示：辩论结束后您可以追问或要求补充分析
          </p>
        )}
      </div>
    </div>
  )
}

export default DebateChatRoom

