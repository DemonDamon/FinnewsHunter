import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { newsApi, analysisApi } from '@/lib/api-client'
import { formatRelativeTime } from '@/lib/utils'
import { RefreshCw, Sparkles, Calendar, Newspaper, TrendingUp, RefreshCcw, ChevronDown, ChevronUp, CheckCircle2, XCircle, MinusCircle, HelpCircle, Search, X } from 'lucide-react'
import NewsDetailDrawer from '@/components/NewsDetailDrawer'
import { useNewsToolbar } from '@/context/NewsToolbarContext'
import { useDebounce } from '@/hooks/useDebounce'
import HighlightText from '@/components/HighlightText'
import { useModelConfig } from '@/components/ModelSelector'
import { useGlobalI18n } from '@/store/useLanguageStore'

type FilterType = 'all' | 'pending' | 'positive' | 'negative' | 'neutral'

// 独立的搜索框组件，自己管理内部状态，避免每次输入都重新挂载
function SearchBox({ onSearch }: { onSearch: (query: string) => void }) {
  const t = useGlobalI18n()
  const [localQuery, setLocalQuery] = useState('')
  const isComposingRef = useRef(false)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setLocalQuery(value)
    // 非组合输入状态下，直接更新搜索词
    if (!isComposingRef.current) {
      onSearch(value)
    }
  }

  const handleCompositionEnd = (e: React.CompositionEvent<HTMLInputElement>) => {
    isComposingRef.current = false
    // 组合输入结束后，更新搜索词
    onSearch(e.currentTarget.value)
  }

  const handleClear = () => {
    setLocalQuery('')
    onSearch('')
  }

  return (
    <div className="relative w-full">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
      <input
        type="text"
        placeholder={t.news.search}
        value={localQuery}
        onCompositionStart={() => {
          isComposingRef.current = true
        }}
        onCompositionEnd={handleCompositionEnd}
        onChange={handleChange}
        className="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 h-10"
      />
      {localQuery && (
        <button
          onClick={handleClear}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
          aria-label="清除搜索"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}

// 新闻源配置（国际化在组件内处理）
const NEWS_SOURCES = [
  { key: 'all', nameZh: '全部来源', nameEn: 'All Sources', icon: '📰' },
  { key: 'sina', nameZh: '新浪财经', nameEn: 'Sina Finance', icon: '🌐' },
  { key: 'tencent', nameZh: '腾讯财经', nameEn: 'Tencent Finance', icon: '🐧' },
  { key: 'jwview', nameZh: '金融界', nameEn: 'JRJ', icon: '💰' },
  { key: 'eeo', nameZh: '经济观察网', nameEn: 'EEO', icon: '📊' },
  { key: 'caijing', nameZh: '财经网', nameEn: 'Caijing', icon: '📈' },
  { key: 'jingji21', nameZh: '21经济网', nameEn: '21Jingji', icon: '📉' },
  { key: 'nbd', nameZh: '每日经济新闻', nameEn: 'NBD', icon: '📰' },
  { key: 'yicai', nameZh: '第一财经', nameEn: 'Yicai', icon: '🎯' },
  { key: '163', nameZh: '网易财经', nameEn: '163 Finance', icon: '📧' },
  { key: 'eastmoney', nameZh: '东方财富', nameEn: 'Eastmoney', icon: '💎' },
]

// 后端可能返回的中文 source 名称到 key 的映射
const SOURCE_NAME_TO_KEY: Record<string, string> = {
  '全部来源': 'all',
  '新浪财经': 'sina',
  '腾讯财经': 'tencent',
  '金融界': 'jwview',
  '经济观察网': 'eeo',
  '财经网': 'caijing',
  '21经济网': 'jingji21',
  '每日经济新闻': 'nbd',
  '第一财经': 'yicai',
  '网易财经': '163',
  '东方财富': 'eastmoney',
  '东方财富网': 'eastmoney', // 后端可能返回的变体
  '同花顺财经': 'tonghuashun', // 后端可能返回的其他来源
  '证券时报': 'securities_times',
  '证券之星': 'stockstar',
  '中金在线': 'cnfol',
  '澎湃新闻': 'thepaper',
  '证券时报网': 'securities_times_online',
  '北京商报': 'bbtnews',
  '卡车之家': 'truckhome',
  'sogou': 'sogou',
}

// 扩展的新闻源配置（包含后端可能返回的其他来源）
const EXTENDED_NEWS_SOURCES: Record<string, { nameZh: string; nameEn: string; icon: string }> = {
  tonghuashun: { nameZh: '同花顺财经', nameEn: 'Tonghuashun Finance', icon: '📊' },
  securities_times: { nameZh: '证券时报', nameEn: 'Securities Times', icon: '📰' },
  stockstar: { nameZh: '证券之星', nameEn: 'Stockstar', icon: '⭐' },
  cnfol: { nameZh: '中金在线', nameEn: 'CNFOL', icon: '💼' },
  thepaper: { nameZh: '澎湃新闻', nameEn: 'The Paper', icon: '📰' },
  securities_times_online: { nameZh: '证券时报网', nameEn: 'Securities Times Online', icon: '📰' },
  bbtnews: { nameZh: '北京商报', nameEn: 'Beijing Business Today', icon: '📰' },
  truckhome: { nameZh: '卡车之家', nameEn: 'Truck Home', icon: '🚚' },
  sogou: { nameZh: '搜狗', nameEn: 'Sogou', icon: '🔍' },
}

export default function NewsListPage() {
  const t = useGlobalI18n()
  const queryClient = useQueryClient()
  const [expandedStocks, setExpandedStocks] = useState<Set<number>>(new Set())
  const [gridCols, setGridCols] = useState(3)
  const [activeFilter, setActiveFilter] = useState<FilterType>('all')
  const [activeSource, setActiveSource] = useState<string>('all') // 新增：来源筛选
  const [analyzingNewsId, setAnalyzingNewsId] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false) // 手动管理刷新状态
  const [selectedNewsId, setSelectedNewsId] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('') // 搜索关键词
  const debouncedSearchQuery = useDebounce(searchQuery, 300) // 防抖处理
  
  // 获取新闻源图标
  const getSourceIcon = useCallback((sourceValue: string) => {
    // 1. 先尝试直接匹配 key
    const sourceByKey = NEWS_SOURCES.find(s => s.key === sourceValue)
    if (sourceByKey) {
      return sourceByKey.icon
    }
    
    // 2. 尝试通过中文名称映射到 key
    const mappedKey = SOURCE_NAME_TO_KEY[sourceValue]
    if (mappedKey) {
      const source = NEWS_SOURCES.find(s => s.key === mappedKey)
      if (source) {
        return source.icon
      }
      // 如果在扩展配置中
      const extendedSource = EXTENDED_NEWS_SOURCES[mappedKey]
      if (extendedSource) {
        return extendedSource.icon
      }
    }
    
    // 3. 尝试在扩展配置中直接查找
    const extendedSource = EXTENDED_NEWS_SOURCES[sourceValue]
    if (extendedSource) {
      return extendedSource.icon
    }
    
    // 4. 默认图标
    return '📰'
  }, [])
  
  // 获取新闻源名称（支持中文 source 名称映射）
  const getSourceName = useCallback((sourceValue: string) => {
    // 1. 先尝试直接匹配 key
    const sourceByKey = NEWS_SOURCES.find(s => s.key === sourceValue)
    if (sourceByKey) {
      return t.nav.home === '首页' ? sourceByKey.nameZh : sourceByKey.nameEn
    }
    
    // 2. 尝试通过中文名称映射到 key
    const mappedKey = SOURCE_NAME_TO_KEY[sourceValue]
    if (mappedKey) {
      const source = NEWS_SOURCES.find(s => s.key === mappedKey)
      if (source) {
        return t.nav.home === '首页' ? source.nameZh : source.nameEn
      }
      // 如果在扩展配置中
      const extendedSource = EXTENDED_NEWS_SOURCES[mappedKey]
      if (extendedSource) {
        return t.nav.home === '首页' ? extendedSource.nameZh : extendedSource.nameEn
      }
    }
    
    // 3. 尝试在扩展配置中直接查找
    const extendedSource = EXTENDED_NEWS_SOURCES[sourceValue]
    if (extendedSource) {
      return t.nav.home === '首页' ? extendedSource.nameZh : extendedSource.nameEn
    }
    
    // 4. 如果都不匹配，返回原值（可能是英文或未知来源）
    return sourceValue
  }, [t])
  
  // 使用 useCallback 确保 onSearch 引用稳定，避免 SearchBox 重新渲染
  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query)
  }, [])
  const { setContent } = useNewsToolbar()
  const modelConfig = useModelConfig() // 获取当前选中的模型配置

  // 监听自定义事件，用于从相关新闻跳转
  useEffect(() => {
    const handleNewsSelect = (e: CustomEvent<number>) => {
      setSelectedNewsId(e.detail)
      setDrawerOpen(true)
    }
    window.addEventListener('news-select', handleNewsSelect as EventListener)
    return () => {
      window.removeEventListener('news-select', handleNewsSelect as EventListener)
    }
  }, [])

  // Phase 2: 自动轮询最新新闻（1分钟刷新）
  const { data: newsList, isLoading } = useQuery({
    queryKey: ['news', 'latest', activeSource],
    queryFn: () => newsApi.getLatestNews({ 
      source: activeSource === 'all' ? undefined : activeSource, 
      limit: 200  // 增加限制以显示更多新闻
    }),
    staleTime: 1 * 60 * 1000,  // 1分钟内数据视为新鲜
    refetchInterval: 1 * 60 * 1000,  // 每1分钟自动刷新
    refetchIntervalInBackground: true,  // 后台也刷新
  })

  // 这里保留 dataUpdatedAt，后续可以用于全局最后刷新时间展示

  // Phase 2: 强制刷新 mutation
  const refreshMutation = useMutation({
    mutationFn: newsApi.forceRefresh,
    onSuccess: () => {
      toast.success('爬取任务已触发，正在获取最新新闻...')
      // 等待更长时间让爬取完成（根据日志，爬取大约需要60-120秒）
      const checkInterval = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ['news', 'latest'] })
      }, 5000) // 每5秒检查一次
      
      // 2分钟后停止轮询并结束
      setTimeout(() => {
        clearInterval(checkInterval)
        queryClient.invalidateQueries({ queryKey: ['news', 'latest'] })
        setIsRefreshing(false) // 结束刷新状态
        toast.success('刷新完成！')
      }, 120000) // 120秒
    },
    onError: (error: Error) => {
      setIsRefreshing(false) // 出错也要结束刷新状态
      toast.error(`刷新失败: ${error.message}`)
    },
  })

  // 分析新闻 mutation
  const analyzeMutation = useMutation({
    mutationFn: (newsId: number) => analysisApi.analyzeNews(newsId, modelConfig),
    onSuccess: (data) => {
      setAnalyzingNewsId(null)
      if (data.success) {
        toast.success(t.news.analysisComplete)
        queryClient.invalidateQueries({ queryKey: ['news'] })
      } else {
        toast.error(`${t.news.analysisFailed}: ${data.error}`)
      }
    },
    onError: (error: Error) => {
      setAnalyzingNewsId(null)
      toast.error(`${t.news.analysisFailed}: ${error.message}`)
    },
  })

  const handleForceRefresh = () => {
    if (isRefreshing) {
      toast.warning(t.news.crawling)
      return
    }
    
    setIsRefreshing(true) // 立即设置刷新状态，阻止后续点击
    refreshMutation.mutate({ source: 'sina' })
  }

  // 将搜索框 + 刷新按钮挂到顶部工具栏
  useEffect(() => {
    // 使用独立的 SearchBox 组件，它自己管理内部状态
    // 这样 searchQuery 变化时不会导致 input 重新挂载
    const searchBox = <SearchBox onSearch={handleSearch} />

    const refreshButton = (
      <Button
        onClick={handleForceRefresh}
        disabled={isRefreshing}
        variant="outline"
        size="sm"
        className="h-10 rounded-lg border-gray-300 shadow-sm"
      >
        <RefreshCw
          className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`}
        />
        {isRefreshing ? t.news.crawlingProgress : t.news.refreshNow}
      </Button>
    )

    setContent({ left: searchBox, right: refreshButton })

    return () => {
      setContent({ left: null, right: null })
    }
  }, [isRefreshing, setContent, handleSearch])

  const handleAnalyze = (newsId: number) => {
    setAnalyzingNewsId(newsId)
    analyzeMutation.mutate(newsId)
  }

  const toggleStockExpand = (newsId: number) => {
    setExpandedStocks(prev => {
      const newSet = new Set(prev)
      if (newSet.has(newsId)) {
        newSet.delete(newsId)
      } else {
        newSet.add(newsId)
      }
      return newSet
    })
  }

  // 动态计算每行卡片数量，使卡片尽可能接近正方形
  useEffect(() => {
    const calculateGridCols = () => {
      const containerWidth = window.innerWidth - 48 // 减去左右 padding (24px * 2)
      const idealCardWidth = 380 // 理想卡片宽度，接近 min-h-[480px] 形成正方形
      const gap = 24 // gap-6 = 24px
      
      // 计算可以放下多少列
      let cols = Math.floor((containerWidth + gap) / (idealCardWidth + gap))
      
      // 限制在合理范围内
      cols = Math.max(1, Math.min(cols, 5))
      
      setGridCols(cols)
    }

    calculateGridCols()
    window.addEventListener('resize', calculateGridCols)
    return () => window.removeEventListener('resize', calculateGridCols)
  }, [])

  // 根据股票数量动态计算内容显示行数
  const getContentLines = (stockCount: number, isExpanded: boolean) => {
    if (stockCount === 0) {
      return 8 // 没有股票时显示更多内容
    }
    if (isExpanded || stockCount > 6) {
      return 3 // 展开或股票很多时显示较少内容
    }
    if (stockCount <= 3) {
      return 6 // 股票很少时显示更多内容
    }
    return 5 // 默认中等内容
  }

  const getSentimentBadge = (score: number | null) => {
    if (score === null) return null
    if (score > 0.1) {
      return (
        <Badge className="bg-green-100 text-green-800 hover:bg-green-100 border-green-200">
          <span className="mr-1">😊</span>
          {t.news.positive} {score.toFixed(2)}
        </Badge>
      )
    }
    if (score < -0.1) {
      return (
        <Badge className="bg-red-100 text-red-800 hover:bg-red-100 border-red-200">
          <span className="mr-1">😰</span>
          {t.news.negative} {score.toFixed(2)}
        </Badge>
      )
    }
    return (
      <Badge variant="outline" className="bg-gray-50 text-gray-700">
        <span className="mr-1">😐</span>
        {t.news.neutral} {score.toFixed(2)}
      </Badge>
    )
  }

  // 筛选新闻（情感 + 搜索）
  const filteredNews = useMemo(() => {
    if (!newsList) return []
    
    const query = debouncedSearchQuery.toLowerCase().trim()
    
    return newsList.filter(news => {
      // 1. 情感筛选
      let sentimentMatch = true
      switch (activeFilter) {
        case 'pending':
          sentimentMatch = news.sentiment_score === null
          break
        case 'positive':
          sentimentMatch = news.sentiment_score !== null && news.sentiment_score > 0.1
          break
        case 'negative':
          sentimentMatch = news.sentiment_score !== null && news.sentiment_score < -0.1
          break
        case 'neutral':
          sentimentMatch = news.sentiment_score !== null && news.sentiment_score >= -0.1 && news.sentiment_score <= 0.1
          break
        default:
          sentimentMatch = true
      }
      
      // 2. 搜索匹配（如果没有搜索词，则自动通过）
      if (!query) return sentimentMatch
      
      const titleMatch = news.title.toLowerCase().includes(query)
      const contentMatch = news.content.toLowerCase().includes(query)
      const codeMatch = news.stock_codes?.some(code => code.toLowerCase().includes(query)) || false
      const sourceMatch = getSourceName(news.source).toLowerCase().includes(query)
      
      const searchMatch = titleMatch || contentMatch || codeMatch || sourceMatch
      
      // 3. 返回交集
      return sentimentMatch && searchMatch
    })
  }, [newsList, activeFilter, debouncedSearchQuery, getSourceName])

  // 获取卡片样式类
  const getCardStyle = (sentiment: number | null) => {
    const baseStyle = "flex flex-col transition-all duration-300 border min-w-0 h-full hover:shadow-lg hover:-translate-y-1"
    
    if (sentiment === null) {
      return `${baseStyle} bg-white border-gray-200 hover:border-primary/30`
    }

    if (sentiment > 0.1) {
      // 利好：鲜明的绿色渐变背景 + 深绿边框
      return `${baseStyle} bg-gradient-to-br from-emerald-100 to-white border-emerald-300 hover:border-emerald-400 hover:shadow-emerald-200/60`
    }
    
    if (sentiment < -0.1) {
      // 利空：鲜明的红色渐变背景 + 深红边框
      return `${baseStyle} bg-gradient-to-br from-rose-100 to-white border-rose-300 hover:border-rose-400 hover:shadow-rose-200/60`
    }

    // 中性：清晰的蓝色/灰色渐变背景 + 深灰边框
    return `${baseStyle} bg-gradient-to-br from-slate-100 to-white border-slate-300 hover:border-slate-400 hover:shadow-slate-200/60`
  }

  // 获取重新分析按钮样式
  const getAnalyzeButtonStyle = (sentiment: number | null) => {
    if (sentiment === null) {
      return "w-full bg-primary hover:bg-primary/90 text-white shadow-sm hover:shadow transition-all"
    }
    if (sentiment > 0.1) {
      return "w-full border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-800 transition-colors"
    }
    if (sentiment < -0.1) {
      return "w-full border-rose-200 text-rose-700 hover:bg-rose-50 hover:border-rose-300 hover:text-rose-800 transition-colors"
    }
    return "w-full border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300 hover:text-slate-800 transition-colors"
  }

  return (
    <div className="p-6 space-y-6">
      {/* 筛选栏：新闻源 + 情感筛选 */}
      <Card className="border-gray-200 shadow-sm">
        <CardHeader className="pb-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* 新闻源筛选 */}
            <div className="flex flex-wrap items-center gap-1.5 bg-blue-50 p-1 rounded-lg border border-blue-200">
              {NEWS_SOURCES.map((source) => (
                <Button
                  key={source.key}
                  variant={activeSource === source.key ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveSource(source.key)}
                  className={
                    activeSource === source.key
                      ? 'bg-white text-blue-600 shadow-sm hover:bg-white/90 text-xs'
                      : 'text-slate-600 hover:text-blue-600 text-xs'
                  }
                >
                  <span className="mr-1">{source.icon}</span>
                  {getSourceName(source.key)}
                </Button>
              ))}
            </div>
            
            {/* 情感筛选 */}
            <div className="flex flex-wrap items-center gap-1 bg-slate-50 p-1 rounded-lg border border-slate-200">
                <Button
                  variant={activeFilter === 'all' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('all')}
                className={`h-8 ${
                  activeFilter === 'all'
                    ? 'bg-white text-primary shadow-sm hover:bg-white/90'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
                >
                  {t.news.all}
                </Button>
                <Button
                  variant={activeFilter === 'pending' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('pending')}
                className={`h-8 ${
                  activeFilter === 'pending'
                    ? 'bg-white text-orange-600 shadow-sm hover:bg-white/90'
                    : 'text-slate-600 hover:text-orange-600'
                }`}
                >
                  <HelpCircle className="w-3.5 h-3.5 mr-1.5" />
                  {t.news.pending}
                </Button>
                <Button
                  variant={activeFilter === 'positive' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('positive')}
                className={`h-8 ${
                  activeFilter === 'positive'
                    ? 'bg-white text-emerald-600 shadow-sm hover:bg-white/90'
                    : 'text-slate-600 hover:text-emerald-600'
                }`}
                >
                  <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                  {t.news.positive}
                </Button>
                <Button
                  variant={activeFilter === 'negative' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('negative')}
                className={`h-8 ${
                  activeFilter === 'negative'
                    ? 'bg-white text-rose-600 shadow-sm hover:bg-white/90'
                    : 'text-slate-600 hover:text-rose-600'
                }`}
                >
                  <XCircle className="w-3.5 h-3.5 mr-1.5" />
                  {t.news.negative}
                </Button>
                <Button
                  variant={activeFilter === 'neutral' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('neutral')}
                className={`h-8 ${
                  activeFilter === 'neutral'
                    ? 'bg-white text-slate-600 shadow-sm hover:bg-white/90'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
                >
                  <MinusCircle className="w-3.5 h-3.5 mr-1.5" />
                  {t.news.neutral}
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* 新闻统计 */}
      {!isLoading && filteredNews && filteredNews.length > 0 && (
        <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
          <CardContent className="py-4">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold text-blue-600">{filteredNews.length}</span>
                  <span className="text-sm text-gray-600">{t.news.items}</span>
                </div>
                {activeSource === 'all' && filteredNews && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-600">{t.news.source}：</span>
                    <div className="flex flex-wrap gap-1">
                      {Array.from(new Set(filteredNews.map(n => n.source))).map(source => (
                        <Badge key={source} variant="outline" className="text-xs">
                          <span className="mr-0.5">{getSourceIcon(source)}</span>
                          {getSourceName(source)}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="text-xs text-gray-500 flex flex-wrap gap-2">
                {debouncedSearchQuery && (
                  <span className="bg-blue-100 text-blue-700 px-2 py-1 rounded">
                    🔍 "{debouncedSearchQuery}"
                  </span>
                )}
                {activeFilter !== 'all' && (
                  <span>
                    {activeFilter === 'pending' ? t.news.pending : activeFilter === 'positive' ? t.news.positive : activeFilter === 'negative' ? t.news.negative : t.news.neutral}
                  </span>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 新闻列表 */}
      <div 
        className="grid gap-6"
        style={{
          gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))`
        }}
      >
        {isLoading ? (
          <div className="col-span-full text-center py-12 text-gray-500">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            <p className="mt-4">{t.common.loading}</p>
          </div>
        ) : filteredNews && filteredNews.length > 0 ? (
          filteredNews.map((news) => (
            <Card 
              key={news.id} 
              className={`${getCardStyle(news.sentiment_score)} cursor-pointer hover:shadow-lg transition-shadow`}
              onClick={(e) => {
                // 阻止按钮点击事件冒泡
                if ((e.target as HTMLElement).closest('button')) {
                  return
                }
                setSelectedNewsId(news.id)
                setDrawerOpen(true)
              }}
            >
              <CardHeader className="pb-2 flex-shrink-0">
                <CardTitle className="text-base leading-tight font-semibold text-gray-900 line-clamp-2 mb-1.5 min-h-[44px]">
                  <HighlightText text={news.title} highlight={debouncedSearchQuery} />
                </CardTitle>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <div className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    <span>{formatRelativeTime(news.publish_time || news.created_at, t.time)}</span>
                  </div>
                  <span>•</span>
                  <div className="flex items-center gap-1">
                    <span>{getSourceIcon(news.source)}</span>
                    <span>{getSourceName(news.source)}</span>
                  </div>
                </div>
              </CardHeader>
              
              <CardContent className="flex-1 flex flex-col pb-3 pt-2 overflow-hidden">
                <div 
                  className="text-sm text-gray-600 mb-3 leading-relaxed flex-shrink-0"
                  style={{
                    display: '-webkit-box',
                    WebkitLineClamp: getContentLines(
                      news.stock_codes?.length || 0,
                      expandedStocks.has(news.id)
                    ),
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden'
                  }}
                >
                  <HighlightText text={news.content} highlight={debouncedSearchQuery} />
                </div>
                
                <div className="mt-auto space-y-2">
                  {news.stock_codes && news.stock_codes.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="flex flex-wrap gap-1.5">
                        {(expandedStocks.has(news.id) 
                          ? news.stock_codes 
                          : news.stock_codes.slice(0, 6)
                        ).map((code) => (
                          <Badge 
                            key={code} 
                            variant="outline" 
                            className="text-xs bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100 px-2 py-0.5"
                          >
                            <TrendingUp className="w-3 h-3 mr-0.5" />
                            {code}
                          </Badge>
                        ))}
                      </div>
                      {news.stock_codes.length > 6 && (
                        <button
                          onClick={() => toggleStockExpand(news.id)}
                          className="text-xs text-primary hover:text-primary/80 flex items-center gap-0.5 transition-colors pt-0.5"
                        >
                          {expandedStocks.has(news.id) ? (
                            <>
                              <ChevronUp className="w-3 h-3" />
                              {t.news.collapse} ({news.stock_codes.length} {t.news.stocks})
                            </>
                          ) : (
                            <>
                              <ChevronDown className="w-3 h-3" />
                              {t.news.expandMore} ({news.stock_codes.length - 6})
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  )}

                  {news.sentiment_score !== null && (
                    <div className="flex items-center pt-0.5">
                      {getSentimentBadge(news.sentiment_score)}
                    </div>
                  )}
                </div>
              </CardContent>

              <CardFooter className="pt-2 pb-4 px-6 flex-shrink-0">
                <Button
                  onClick={() => handleAnalyze(news.id)}
                  disabled={analyzingNewsId === news.id}
                  size="sm"
                  className={getAnalyzeButtonStyle(news.sentiment_score)}
                  variant={news.sentiment_score !== null ? 'outline' : 'default'}
                >
                  {analyzingNewsId === news.id ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      {t.news.analyzing}
                    </>
                  ) : news.sentiment_score !== null ? (
                    <>
                      <RefreshCcw className="w-4 h-4 mr-2" />
                      {t.news.reanalyze}
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4 mr-2" />
                      {t.news.analyze}
                    </>
                  )}
                </Button>
              </CardFooter>
            </Card>
          ))
        ) : (
          <div className="col-span-full text-center py-16">
            <div className="text-gray-400 mb-2">
              {debouncedSearchQuery ? (
                <Search className="w-16 h-16 mx-auto opacity-50" />
              ) : (
              <Newspaper className="w-16 h-16 mx-auto opacity-50" />
              )}
            </div>
            {debouncedSearchQuery ? (
              <>
                <p className="text-gray-500 text-lg">{t.news.noNewsFound} "{debouncedSearchQuery}" {t.news.relatedNews}</p>
                <p className="text-gray-400 text-sm mt-1">{t.news.tryOtherKeywords}</p>
              </>
            ) : (
              <>
            <p className="text-gray-500 text-lg">{t.news.noNews}</p>
            <p className="text-gray-400 text-sm mt-1">{t.news.pleaseCrawl}</p>
              </>
            )}
          </div>
        )}
      </div>

      {/* 新闻详情抽屉 */}
      <NewsDetailDrawer
        newsId={selectedNewsId}
        open={drawerOpen}
        onOpenChange={(open) => {
          setDrawerOpen(open)
          if (!open) {
            // 延迟清除newsId，避免关闭动画时闪烁
            setTimeout(() => setSelectedNewsId(null), 300)
          }
        }}
      />
    </div>
  )
}

