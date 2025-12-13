/**
 * 股票搜索组件
 * 支持代码和名称模糊搜索
 */
import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { stockApi } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { Search, Loader2, Database, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

interface StockSearchProps {
  className?: string
  placeholder?: string
  onSelect?: (stock: { code: string; name: string; full_code: string }) => void
}

export default function StockSearch({
  className,
  placeholder = '搜索股票代码或名称...',
  onSelect,
}: StockSearchProps) {
  const [keyword, setKeyword] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // 获取股票数量
  const { data: stockCount } = useQuery({
    queryKey: ['stock-count'],
    queryFn: () => stockApi.getStockCount(),
    staleTime: 60 * 1000,
  })

  // 初始化股票数据
  const initMutation = useMutation({
    mutationFn: () => stockApi.initStockData(),
    onSuccess: (data) => {
      if (data.success) {
        toast.success(`成功导入 ${data.count} 只股票！`)
        queryClient.invalidateQueries({ queryKey: ['stock-count'] })
        queryClient.invalidateQueries({ queryKey: ['stock-search'] })
      } else {
        toast.error(data.message)
      }
    },
    onError: (error: Error) => {
      toast.error(`初始化失败: ${error.message}`)
    },
  })

  // 搜索查询
  const { data: searchResults, isLoading } = useQuery({
    queryKey: ['stock-search', keyword],
    queryFn: () => stockApi.searchRealtime(keyword, 15),
    enabled: keyword.length >= 1,
    staleTime: 30 * 1000,
  })

  // 处理选择股票
  const handleSelect = useCallback((stock: { code: string; name: string; full_code: string }) => {
    setKeyword('')
    setIsOpen(false)
    setSelectedIndex(-1)
    
    if (onSelect) {
      onSelect(stock)
    } else {
      // 默认跳转到股票分析页面
      navigate(`/stock/${stock.full_code}`)
    }
  }, [navigate, onSelect])

  // 键盘导航
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!searchResults || searchResults.length === 0) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(prev => 
          prev < searchResults.length - 1 ? prev + 1 : 0
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(prev => 
          prev > 0 ? prev - 1 : searchResults.length - 1
        )
        break
      case 'Enter':
        e.preventDefault()
        if (selectedIndex >= 0 && searchResults[selectedIndex]) {
          handleSelect(searchResults[selectedIndex])
        }
        break
      case 'Escape':
        setIsOpen(false)
        setSelectedIndex(-1)
        break
    }
  }, [searchResults, selectedIndex, handleSelect])

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        inputRef.current &&
        !inputRef.current.contains(e.target as Node) &&
        listRef.current &&
        !listRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 滚动到选中项
  useEffect(() => {
    if (selectedIndex >= 0 && listRef.current) {
      const selectedItem = listRef.current.children[selectedIndex] as HTMLElement
      if (selectedItem) {
        selectedItem.scrollIntoView({ block: 'nearest' })
      }
    }
  }, [selectedIndex])

  return (
    <div className={cn('relative', className)}>
      {/* 搜索输入框 */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value)
            setIsOpen(true)
            setSelectedIndex(-1)
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={cn(
            'w-full pl-10 pr-4 py-2.5 text-sm',
            'border border-gray-200 rounded-lg',
            'focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400',
            'placeholder:text-gray-400',
            'transition-all duration-200'
          )}
        />
        {isLoading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 animate-spin" />
        )}
      </div>

      {/* 搜索结果下拉列表 */}
      {isOpen && keyword.length >= 1 && (
        <div
          ref={listRef}
          className={cn(
            'absolute z-50 w-full mt-1',
            'bg-white rounded-lg shadow-lg border border-gray-100',
            'max-h-[400px] overflow-y-auto',
            'animate-in fade-in-0 zoom-in-95 duration-150'
          )}
        >
          {isLoading ? (
            <div className="flex items-center justify-center py-8 text-gray-500">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              搜索中...
            </div>
          ) : searchResults && searchResults.length > 0 ? (
            <div className="py-1">
              {searchResults.map((stock, index) => (
                <div
                  key={stock.code}
                  onClick={() => handleSelect(stock)}
                  className={cn(
                    'flex items-center justify-between px-4 py-3 cursor-pointer',
                    'transition-colors duration-100',
                    selectedIndex === index
                      ? 'bg-blue-50'
                      : 'hover:bg-gray-50'
                  )}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex flex-col">
                      <span className="font-medium text-gray-900">
                        {stock.name}
                      </span>
                      <span className="text-xs text-gray-500">
                        {stock.full_code}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {stock.market && (
                      <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                        {stock.market}
                      </span>
                    )}
                    {stock.industry && (
                      <span className="text-xs text-gray-500">
                        {stock.industry}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-6 text-center">
              {stockCount && stockCount.count === 0 ? (
                // 数据库为空时显示初始化按钮
                <div className="space-y-3">
                  <Database className="w-10 h-10 mx-auto text-gray-300" />
                  <p className="text-gray-500">股票数据库为空</p>
                  <p className="text-sm text-gray-400">点击下方按钮初始化股票数据</p>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      initMutation.mutate()
                    }}
                    disabled={initMutation.isPending}
                    className={cn(
                      'inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg',
                      'bg-blue-600 text-white hover:bg-blue-700',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                      'transition-colors'
                    )}
                  >
                    {initMutation.isPending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        正在导入股票数据...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-4 h-4" />
                        初始化股票数据
                      </>
                    )}
                  </button>
                </div>
              ) : (
                // 有数据但没有匹配结果
                <div>
                  <p className="text-gray-500">未找到匹配的股票</p>
                  <p className="text-sm text-gray-400 mt-1">尝试输入股票代码或名称</p>
                </div>
              )}
            </div>
          )}
          
          {/* 快捷提示 */}
          <div className="px-4 py-2 border-t border-gray-100 bg-gray-50/50">
            <div className="flex items-center gap-4 text-xs text-gray-400">
              <span>
                <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">↑↓</kbd> 导航
              </span>
              <span>
                <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">Enter</kbd> 选择
              </span>
              <span>
                <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">Esc</kbd> 关闭
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

