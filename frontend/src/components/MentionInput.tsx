import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { 
  TrendingUp, 
  TrendingDown, 
  Briefcase, 
  Search, 
  Database, 
  Globe, 
  Chrome,
  Bot,
  Hash,
  X
} from 'lucide-react'
import { cn } from '@/lib/utils'

// 可提及的目标类型
export type MentionType = 'agent' | 'source' | 'stock'

export interface MentionTarget {
  type: MentionType
  id: string
  label: string
  description?: string
  icon: React.ReactNode
  color: string
}

// 预定义的智能体列表
const AGENTS: MentionTarget[] = [
  { 
    type: 'agent', 
    id: 'bull', 
    label: '多方辩手', 
    description: '分析看多因素',
    icon: <TrendingUp className="w-4 h-4" />,
    color: 'text-emerald-600 bg-emerald-50'
  },
  { 
    type: 'agent', 
    id: 'bear', 
    label: '空方辩手', 
    description: '分析看空因素',
    icon: <TrendingDown className="w-4 h-4" />,
    color: 'text-rose-600 bg-rose-50'
  },
  { 
    type: 'agent', 
    id: 'manager', 
    label: '投资经理', 
    description: '综合决策',
    icon: <Briefcase className="w-4 h-4" />,
    color: 'text-indigo-600 bg-indigo-50'
  },
  { 
    type: 'agent', 
    id: 'data_collector', 
    label: '数据专员', 
    description: '收集市场数据/动态搜索',
    icon: <Bot className="w-4 h-4" />,
    color: 'text-cyan-600 bg-cyan-50'
  },
]

// 预定义的数据源列表
const SOURCES: MentionTarget[] = [
  { 
    type: 'source', 
    id: 'akshare', 
    label: 'AkShare', 
    description: '金融数据接口',
    icon: <Database className="w-4 h-4" />,
    color: 'text-blue-600 bg-blue-50'
  },
  { 
    type: 'source', 
    id: 'bochaai', 
    label: 'BochaAI', 
    description: '实时新闻搜索',
    icon: <Globe className="w-4 h-4" />,
    color: 'text-orange-600 bg-orange-50'
  },
  { 
    type: 'source', 
    id: 'browser', 
    label: '网页搜索', 
    description: '多引擎网页搜索',
    icon: <Chrome className="w-4 h-4" />,
    color: 'text-green-600 bg-green-50'
  },
  { 
    type: 'source', 
    id: 'kb', 
    label: '知识库', 
    description: '历史新闻数据',
    icon: <Hash className="w-4 h-4" />,
    color: 'text-amber-600 bg-amber-50'
  },
]

// 所有可提及目标
const ALL_TARGETS = [...AGENTS, ...SOURCES]

interface MentionInputProps {
  value: string
  onChange: (value: string) => void
  onSubmit: (value: string, mentions: MentionTarget[]) => void
  placeholder?: string
  disabled?: boolean
  className?: string
  // 可选：动态股票列表
  stockOptions?: Array<{ code: string; name: string }>
}

const MentionInput: React.FC<MentionInputProps> = ({
  value,
  onChange,
  onSubmit,
  placeholder = '输入消息，使用 @ 提及智能体或数据源...',
  disabled = false,
  className,
  stockOptions = []
}) => {
  const [showPopup, setShowPopup] = useState(false)
  const [popupPosition, setPopupPosition] = useState({ top: 0, left: 0 })
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionStartPos, setMentionStartPos] = useState(-1)
  const [activeMentions, setActiveMentions] = useState<MentionTarget[]>([])
  
  const inputRef = useRef<HTMLInputElement>(null)
  const popupRef = useRef<HTMLDivElement>(null)
  
  // 合并股票选项到目标列表
  const allTargets = useMemo(() => {
    const stockTargets: MentionTarget[] = stockOptions.map(s => ({
      type: 'stock' as MentionType,
      id: s.code,
      label: s.name,
      description: s.code,
      icon: <Hash className="w-4 h-4" />,
      color: 'text-gray-600 bg-gray-50'
    }))
    return [...ALL_TARGETS, ...stockTargets]
  }, [stockOptions])
  
  // 过滤后的目标列表
  const filteredTargets = useMemo(() => {
    if (!mentionQuery) return allTargets
    const query = mentionQuery.toLowerCase()
    return allTargets.filter(t => 
      t.label.toLowerCase().includes(query) ||
      t.id.toLowerCase().includes(query) ||
      t.description?.toLowerCase().includes(query)
    )
  }, [allTargets, mentionQuery])
  
  // 分组显示
  const groupedTargets = useMemo(() => {
    const agents = filteredTargets.filter(t => t.type === 'agent')
    const sources = filteredTargets.filter(t => t.type === 'source')
    const stocks = filteredTargets.filter(t => t.type === 'stock')
    
    const groups: { label: string; items: MentionTarget[] }[] = []
    if (agents.length > 0) groups.push({ label: '智能体', items: agents })
    if (sources.length > 0) groups.push({ label: '数据源', items: sources })
    if (stocks.length > 0) groups.push({ label: '股票', items: stocks.slice(0, 5) })
    
    return groups
  }, [filteredTargets])
  
  // 扁平化用于键盘导航
  const flatTargets = useMemo(() => {
    return groupedTargets.flatMap(g => g.items)
  }, [groupedTargets])
  
  // 处理输入变化
  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value
    const cursorPos = e.target.selectionStart || 0
    
    onChange(newValue)
    
    // 检测 @ 符号
    const textBeforeCursor = newValue.slice(0, cursorPos)
    const lastAtIndex = textBeforeCursor.lastIndexOf('@')
    
    if (lastAtIndex !== -1) {
      // 检查 @ 后面是否有空格（如果有，说明不是正在输入的提及）
      const textAfterAt = textBeforeCursor.slice(lastAtIndex + 1)
      if (!textAfterAt.includes(' ')) {
        setMentionQuery(textAfterAt)
        setMentionStartPos(lastAtIndex)
        setShowPopup(true)
        setSelectedIndex(0)
        
        // 计算弹窗位置
        if (inputRef.current) {
          const rect = inputRef.current.getBoundingClientRect()
          setPopupPosition({
            top: rect.top - 8, // 在输入框上方显示
            left: rect.left
          })
        }
        return
      }
    }
    
    setShowPopup(false)
    setMentionQuery('')
    setMentionStartPos(-1)
  }, [onChange])
  
  // 选择提及目标
  const selectTarget = useCallback((target: MentionTarget) => {
    if (mentionStartPos === -1) return
    
    const beforeMention = value.slice(0, mentionStartPos)
    const afterMention = value.slice(mentionStartPos + mentionQuery.length + 1) // +1 for @
    const newValue = `${beforeMention}@${target.label} ${afterMention}`
    
    onChange(newValue)
    setActiveMentions(prev => [...prev, target])
    setShowPopup(false)
    setMentionQuery('')
    setMentionStartPos(-1)
    
    // 聚焦回输入框
    inputRef.current?.focus()
  }, [value, mentionStartPos, mentionQuery, onChange])
  
  // 键盘事件处理
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showPopup) {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex(prev => 
            prev < flatTargets.length - 1 ? prev + 1 : 0
          )
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex(prev => 
            prev > 0 ? prev - 1 : flatTargets.length - 1
          )
          break
        case 'Enter':
          e.preventDefault()
          if (flatTargets[selectedIndex]) {
            selectTarget(flatTargets[selectedIndex])
          }
          break
        case 'Escape':
          e.preventDefault()
          setShowPopup(false)
          break
        case 'Tab':
          e.preventDefault()
          if (flatTargets[selectedIndex]) {
            selectTarget(flatTargets[selectedIndex])
          }
          break
      }
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim()) {
        onSubmit(value.trim(), activeMentions)
        setActiveMentions([])
      }
    }
  }, [showPopup, flatTargets, selectedIndex, selectTarget, value, onSubmit, activeMentions])
  
  // 点击外部关闭弹窗
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        popupRef.current && 
        !popupRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setShowPopup(false)
      }
    }
    
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])
  
  // 滚动选中项到可见区域
  useEffect(() => {
    if (showPopup && popupRef.current) {
      const selectedElement = popupRef.current.querySelector(`[data-index="${selectedIndex}"]`)
      selectedElement?.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex, showPopup])
  
  // 移除已添加的提及标签
  const removeMention = useCallback((targetId: string) => {
    const target = activeMentions.find(m => m.id === targetId)
    if (target) {
      const newValue = value.replace(`@${target.label}`, '').replace(/\s+/g, ' ').trim()
      onChange(newValue)
      setActiveMentions(prev => prev.filter(m => m.id !== targetId))
    }
  }, [activeMentions, value, onChange])
  
  return (
    <div className={cn("relative flex-1", className)}>
      {/* 已选择的提及标签 */}
      {activeMentions.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {activeMentions.map(mention => (
            <span 
              key={mention.id}
              className={cn(
                "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
                mention.color
              )}
            >
              {mention.icon}
              {mention.label}
              <button 
                onClick={() => removeMention(mention.id)}
                className="ml-0.5 hover:opacity-70"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      
      {/* 输入框 */}
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        className={cn(
          "w-full px-4 py-2 rounded-full bg-gray-50 border border-gray-200",
          "focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100",
          "text-sm disabled:opacity-50 disabled:cursor-not-allowed",
          "transition-all duration-200"
        )}
      />
      
      {/* @ 提及弹窗 */}
      {showPopup && filteredTargets.length > 0 && (
        <div
          ref={popupRef}
          className={cn(
            "absolute z-50 w-72 max-h-80 overflow-y-auto",
            "bg-white rounded-xl shadow-xl border border-gray-200",
            "animate-in fade-in slide-in-from-bottom-2 duration-200"
          )}
          style={{
            bottom: '100%',
            left: 0,
            marginBottom: '8px'
          }}
        >
          <div className="p-2">
            <div className="text-xs text-gray-400 px-2 py-1 mb-1">
              使用 ↑↓ 选择，Enter 确认，Esc 取消
            </div>
            
            {groupedTargets.map((group, groupIndex) => (
              <div key={group.label} className={groupIndex > 0 ? 'mt-2' : ''}>
                <div className="text-xs font-medium text-gray-500 px-2 py-1 sticky top-0 bg-white">
                  {group.label}
                </div>
                {group.items.map((target, itemIndex) => {
                  const flatIndex = groupedTargets
                    .slice(0, groupIndex)
                    .reduce((acc, g) => acc + g.items.length, 0) + itemIndex
                  
                  return (
                    <button
                      key={target.id}
                      data-index={flatIndex}
                      onClick={() => selectTarget(target)}
                      className={cn(
                        "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left",
                        "transition-colors duration-100",
                        flatIndex === selectedIndex
                          ? "bg-blue-50 text-blue-700"
                          : "hover:bg-gray-50"
                      )}
                    >
                      <div className={cn(
                        "w-8 h-8 rounded-lg flex items-center justify-center",
                        target.color
                      )}>
                        {target.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">
                          {target.label}
                        </div>
                        {target.description && (
                          <div className="text-xs text-gray-500 truncate">
                            {target.description}
                          </div>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* 空结果提示 */}
      {showPopup && filteredTargets.length === 0 && (
        <div
          ref={popupRef}
          className={cn(
            "absolute z-50 w-72",
            "bg-white rounded-xl shadow-xl border border-gray-200 p-4",
            "animate-in fade-in slide-in-from-bottom-2 duration-200"
          )}
          style={{
            bottom: '100%',
            left: 0,
            marginBottom: '8px'
          }}
        >
          <div className="text-sm text-gray-500 text-center">
            未找到匹配的选项
          </div>
        </div>
      )}
    </div>
  )
}

export default MentionInput
export { AGENTS, SOURCES, ALL_TARGETS }

