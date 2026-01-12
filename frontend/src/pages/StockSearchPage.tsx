/**
 * 股票搜索入口页面
 * 风格参考 Manus/ChatGPT 的对话入口
 */
import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { stockApi } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { 
  Search, 
  Loader2, 
  Database, 
  RefreshCw, 
  TrendingUp,
  Sparkles,
  ArrowRight,
  BarChart3
} from 'lucide-react'
import { toast } from 'sonner'
import { useGlobalI18n } from '@/store/useLanguageStore'

export default function StockSearchPage() {
  const t = useGlobalI18n()
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
    navigate(`/stock/${stock.full_code}`)
  }, [navigate])

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

  // 热门股票示例
  const hotStocks = [
    { code: '600519', name: '贵州茅台', full_code: 'SH600519' },
    { code: '000001', name: '平安银行', full_code: 'SZ000001' },
    { code: '601318', name: '中国平安', full_code: 'SH601318' },
    { code: '000858', name: '五粮液', full_code: 'SZ000858' },
  ]

  return (
    <div className="min-h-[calc(100vh-120px)] flex flex-col items-center justify-center px-4 bg-gradient-to-br from-slate-50 via-blue-50/30 to-indigo-50/50">
      {/* 标题区域 */}
      <div className="text-center mb-10 animate-in fade-in-0 slide-in-from-bottom-4 duration-500">
        <div className="flex items-center justify-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/25">
            <BarChart3 className="w-6 h-6 text-white" />
          </div>
        </div>
        <h1 className="text-4xl font-bold text-gray-900 tracking-tight mb-3">
          {t.stock.title}
        </h1>
        <p className="text-lg text-gray-500 max-w-md mx-auto">
          {t.stock.subtitle}
        </p>
      </div>

      {/* 搜索框区域 */}
      <div className="w-full max-w-2xl relative animate-in fade-in-0 slide-in-from-bottom-6 duration-500 delay-100">
        <div className={cn(
          'relative bg-white rounded-2xl shadow-xl shadow-gray-200/50',
          'border border-gray-100',
          'transition-all duration-300',
          isOpen && keyword.length >= 1 ? 'rounded-b-none' : ''
        )}>
          {/* 搜索图标 */}
          <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          
          {/* 输入框 */}
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
            placeholder={t.stock.searchPlaceholder}
            className={cn(
              'w-full pl-14 pr-14 py-5 text-lg',
              'border-none rounded-2xl',
              'focus:outline-none focus:ring-0',
              'placeholder:text-gray-400',
              'transition-all duration-200'
            )}
            autoFocus
          />
          
          {/* 右侧图标 */}
          <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2">
            {isLoading ? (
              <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
            ) : keyword.length > 0 ? (
              <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center cursor-pointer hover:bg-blue-700 transition-colors">
                <ArrowRight className="w-4 h-4 text-white" />
              </div>
            ) : (
              <Sparkles className="w-5 h-5 text-gray-300" />
            )}
          </div>
        </div>

        {/* 搜索结果下拉列表 */}
        {isOpen && keyword.length >= 1 && (
          <div
            ref={listRef}
            className={cn(
              'absolute z-50 w-full',
              'bg-white rounded-b-2xl shadow-xl shadow-gray-200/50',
              'border border-t-0 border-gray-100',
              'max-h-[400px] overflow-y-auto',
              'animate-in fade-in-0 duration-150'
            )}
          >
            {isLoading ? (
              <div className="flex items-center justify-center py-10 text-gray-500">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                {t.stock.searching}
              </div>
            ) : searchResults && searchResults.length > 0 ? (
              <div className="py-2">
                {searchResults.map((stock, index) => (
                  <div
                    key={stock.code}
                    onClick={() => handleSelect(stock)}
                    className={cn(
                      'flex items-center justify-between px-5 py-4 cursor-pointer',
                      'transition-colors duration-100',
                      selectedIndex === index
                        ? 'bg-blue-50'
                        : 'hover:bg-gray-50'
                    )}
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-100 to-indigo-100 flex items-center justify-center">
                        <TrendingUp className="w-5 h-5 text-blue-600" />
                      </div>
                      <div className="flex flex-col">
                        <span className="font-semibold text-gray-900">
                          {stock.name}
                        </span>
                        <span className="text-sm text-gray-500">
                          {stock.full_code}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {stock.market && (
                        <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded-lg">
                          {stock.market}
                        </span>
                      )}
                      {stock.industry && (
                        <span className="text-xs text-gray-500">
                          {stock.industry}
                        </span>
                      )}
                      <ArrowRight className="w-4 h-4 text-gray-300" />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-10 text-center">
                {stockCount && stockCount.count === 0 ? (
                  <div className="space-y-4">
                    <Database className="w-12 h-12 mx-auto text-gray-300" />
                    <p className="text-gray-500 font-medium">{t.stock.emptyDb}</p>
                    <p className="text-sm text-gray-400">{t.stock.initTip}</p>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        initMutation.mutate()
                      }}
                      disabled={initMutation.isPending}
                      className={cn(
                        'inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl',
                        'bg-blue-600 text-white hover:bg-blue-700',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'transition-colors shadow-lg shadow-blue-500/25'
                      )}
                    >
                      {initMutation.isPending ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          {t.stock.importing}
                        </>
                      ) : (
                        <>
                          <RefreshCw className="w-4 h-4" />
                          {t.stock.initBtn}
                        </>
                      )}
                    </button>
                  </div>
                ) : (
                  <div>
                    <p className="text-gray-500 font-medium">{t.stock.notFound}</p>
                    <p className="text-sm text-gray-400 mt-1">{t.stock.tryInput}</p>
                  </div>
                )}
              </div>
            )}
            
            {/* 快捷键提示 */}
            <div className="px-5 py-3 border-t border-gray-100 bg-gray-50/50">
              <div className="flex items-center gap-5 text-xs text-gray-400">
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-gray-500 shadow-sm">↑↓</kbd>
                  <span>{t.stock.nav}</span>
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-gray-500 shadow-sm">Enter</kbd>
                  <span>{t.stock.select}</span>
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-gray-500 shadow-sm">Esc</kbd>
                  <span>{t.stock.close}</span>
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 热门股票推荐 */}
      {!isOpen && (
        <div className="mt-10 animate-in fade-in-0 slide-in-from-bottom-8 duration-500 delay-200">
          <p className="text-sm text-gray-400 text-center mb-4">{t.stock.hotStocks}</p>
          <div className="flex flex-wrap justify-center gap-3">
            {hotStocks.map((stock) => (
              <button
                key={stock.code}
                onClick={() => navigate(`/stock/${stock.full_code}`)}
                className={cn(
                  'flex items-center gap-2 px-4 py-2.5 rounded-xl',
                  'bg-white border border-gray-100 shadow-sm',
                  'hover:border-blue-200 hover:bg-blue-50/50 hover:shadow-md',
                  'transition-all duration-200',
                  'group'
                )}
              >
                <TrendingUp className="w-4 h-4 text-gray-400 group-hover:text-blue-500 transition-colors" />
                <span className="font-medium text-gray-700 group-hover:text-blue-600 transition-colors">
                  {stock.name}
                </span>
                <span className="text-xs text-gray-400">
                  {stock.full_code}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 功能说明 */}
      <div className="mt-16 grid grid-cols-3 gap-8 max-w-2xl animate-in fade-in-0 slide-in-from-bottom-10 duration-500 delay-300">
        <div className="text-center">
          <div className="w-10 h-10 mx-auto rounded-xl bg-blue-100 flex items-center justify-center mb-3">
            <BarChart3 className="w-5 h-5 text-blue-600" />
          </div>
          <p className="text-sm font-medium text-gray-700">{t.stock.kline}</p>
          <p className="text-xs text-gray-400 mt-1">{t.stock.klineDesc}</p>
        </div>
        <div className="text-center">
          <div className="w-10 h-10 mx-auto rounded-xl bg-purple-100 flex items-center justify-center mb-3">
            <Sparkles className="w-5 h-5 text-purple-600" />
          </div>
          <p className="text-sm font-medium text-gray-700">{t.stock.aiSentiment}</p>
          <p className="text-xs text-gray-400 mt-1">{t.stock.aiSentimentDesc}</p>
        </div>
        <div className="text-center">
          <div className="w-10 h-10 mx-auto rounded-xl bg-emerald-100 flex items-center justify-center mb-3">
            <TrendingUp className="w-5 h-5 text-emerald-600" />
          </div>
          <p className="text-sm font-medium text-gray-700">{t.stock.debate}</p>
          <p className="text-xs text-gray-400 mt-1">{t.stock.debateDesc}</p>
        </div>
      </div>
    </div>
  )
}

