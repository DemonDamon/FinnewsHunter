import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { newsApi, analysisApi } from '@/lib/api-client'
import { formatRelativeTime } from '@/lib/utils'
import { Download, RefreshCw, Sparkles, Calendar, Newspaper, TrendingUp, RefreshCcw, ChevronDown, ChevronUp, Filter, CheckCircle2, XCircle, MinusCircle, HelpCircle } from 'lucide-react'
import type { News } from '@/types/api'

type FilterType = 'all' | 'pending' | 'positive' | 'negative' | 'neutral'

// 新闻源配置
const NEWS_SOURCES = [
  { key: 'all', name: '全部来源', icon: '📰' },
  { key: 'sina', name: '新浪财经', icon: '🌐' },
  { key: 'tencent', name: '腾讯财经', icon: '🐧' },
  { key: 'jwview', name: '金融界', icon: '💰' },
  { key: 'eeo', name: '经济观察网', icon: '📊' },
  { key: 'caijing', name: '财经网', icon: '📈' },
  { key: 'jingji21', name: '21经济网', icon: '📉' },
  { key: 'nbd', name: '每日经济新闻', icon: '📰' },
  { key: 'yicai', name: '第一财经', icon: '🎯' },
  { key: '163', name: '网易财经', icon: '📧' },
  { key: 'eastmoney', name: '东方财富', icon: '💎' },
]

export default function NewsListPage() {
  const queryClient = useQueryClient()
  const [expandedStocks, setExpandedStocks] = useState<Set<number>>(new Set())
  const [gridCols, setGridCols] = useState(3)
  const [activeFilter, setActiveFilter] = useState<FilterType>('all')
  const [activeSource, setActiveSource] = useState<string>('all') // 新增：来源筛选
  const [lastUpdateTime, setLastUpdateTime] = useState<string>('')
  const [analyzingNewsId, setAnalyzingNewsId] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false) // 手动管理刷新状态

  // Phase 2: 自动轮询最新新闻（1分钟刷新）
  const { data: newsList, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['news', 'latest', activeSource],
    queryFn: () => newsApi.getLatestNews({ 
      source: activeSource === 'all' ? undefined : activeSource, 
      limit: 200  // 增加限制以显示更多新闻
    }),
    staleTime: 1 * 60 * 1000,  // 1分钟内数据视为新鲜
    refetchInterval: 1 * 60 * 1000,  // 每1分钟自动刷新
    refetchIntervalInBackground: true,  // 后台也刷新
  })

  // 更新最后刷新时间
  useEffect(() => {
    if (dataUpdatedAt) {
      const date = new Date(dataUpdatedAt)
      setLastUpdateTime(date.toLocaleTimeString('zh-CN'))
    }
  }, [dataUpdatedAt])

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
    mutationFn: analysisApi.analyzeNews,
    onSuccess: (data) => {
      setAnalyzingNewsId(null)
      if (data.success) {
        toast.success('分析完成！')
        queryClient.invalidateQueries({ queryKey: ['news'] })
      } else {
        toast.error(`分析失败: ${data.error}`)
      }
    },
    onError: (error: Error) => {
      setAnalyzingNewsId(null)
      toast.error(`分析失败: ${error.message}`)
    },
  })

  const handleForceRefresh = () => {
    if (isRefreshing) {
      toast.warning('正在爬取中，请稍候...')
      return
    }
    
    setIsRefreshing(true) // 立即设置刷新状态，阻止后续点击
    refreshMutation.mutate({ source: 'sina' })
  }

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
          利好 {score.toFixed(2)}
        </Badge>
      )
    }
    if (score < -0.1) {
      return (
        <Badge className="bg-red-100 text-red-800 hover:bg-red-100 border-red-200">
          <span className="mr-1">😰</span>
          利空 {score.toFixed(2)}
        </Badge>
      )
    }
    return (
      <Badge variant="outline" className="bg-gray-50 text-gray-700">
        <span className="mr-1">😐</span>
        中性 {score.toFixed(2)}
      </Badge>
    )
  }

  // 筛选新闻
  const filteredNews = useMemo(() => {
    if (!newsList) return []
    
    return newsList.filter(news => {
      switch (activeFilter) {
        case 'pending':
          return news.sentiment_score === null
        case 'positive':
          return news.sentiment_score !== null && news.sentiment_score > 0.1
        case 'negative':
          return news.sentiment_score !== null && news.sentiment_score < -0.1
        case 'neutral':
          return news.sentiment_score !== null && news.sentiment_score >= -0.1 && news.sentiment_score <= 0.1
        default:
          return true
      }
    })
  }, [newsList, activeFilter])

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
      {/* 操作栏 - Phase 2 简化版 */}
      <Card className="border-gray-200 shadow-sm">
        <CardHeader className="pb-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <CardTitle className="text-xl font-semibold">实时新闻流</CardTitle>
              <p className="text-sm text-muted-foreground">
                自动更新 · 最后刷新：{lastUpdateTime || '加载中...'}
              </p>
            </div>
            
            <div className="flex flex-col gap-3 w-full md:w-auto">
              {/* 来源筛选器 */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-slate-700 mr-2">📰 新闻源：</span>
                <div className="flex flex-wrap items-center gap-1.5 bg-blue-50 p-1 rounded-lg border border-blue-200">
                  {NEWS_SOURCES.map(source => (
                    <Button
                      key={source.key}
                      variant={activeSource === source.key ? 'default' : 'ghost'}
                      size="sm"
                      onClick={() => setActiveSource(source.key)}
                      className={activeSource === source.key 
                        ? 'bg-white text-blue-600 shadow-sm hover:bg-white/90 text-xs' 
                        : 'text-slate-600 hover:text-blue-600 text-xs'
                      }
                    >
                      <span className="mr-1">{source.icon}</span>
                      {source.name}
                    </Button>
                  ))}
                </div>
              </div>
              
              {/* 状态筛选器 */}
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-slate-700 mr-2">📊 情感：</span>
              <div className="flex flex-wrap items-center gap-2 bg-slate-50 p-1 rounded-lg border border-slate-200">
                <Button
                  variant={activeFilter === 'all' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('all')}
                  className={activeFilter === 'all' ? 'bg-white text-primary shadow-sm hover:bg-white/90' : 'text-slate-600 hover:text-slate-900'}
                >
                  全部
                </Button>
                <Button
                  variant={activeFilter === 'pending' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('pending')}
                  className={activeFilter === 'pending' ? 'bg-white text-orange-600 shadow-sm hover:bg-white/90' : 'text-slate-600 hover:text-orange-600'}
                >
                  <HelpCircle className="w-3.5 h-3.5 mr-1.5" />
                  待分析
                </Button>
                <Button
                  variant={activeFilter === 'positive' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('positive')}
                  className={activeFilter === 'positive' ? 'bg-white text-emerald-600 shadow-sm hover:bg-white/90' : 'text-slate-600 hover:text-emerald-600'}
                >
                  <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                  利好
                </Button>
                <Button
                  variant={activeFilter === 'negative' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('negative')}
                  className={activeFilter === 'negative' ? 'bg-white text-rose-600 shadow-sm hover:bg-white/90' : 'text-slate-600 hover:text-rose-600'}
                >
                  <XCircle className="w-3.5 h-3.5 mr-1.5" />
                  利空
                </Button>
                <Button
                  variant={activeFilter === 'neutral' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveFilter('neutral')}
                  className={activeFilter === 'neutral' ? 'bg-white text-slate-600 shadow-sm hover:bg-white/90' : 'text-slate-600 hover:text-slate-900'}
                >
                  <MinusCircle className="w-3.5 h-3.5 mr-1.5" />
                  中性
                </Button>
              </div>
              </div>
              
              {/* 立即刷新按钮 */}
              <Button
                onClick={handleForceRefresh}
                disabled={isRefreshing}
                variant="outline"
                size="sm"
                className="shadow-sm"
              >
                <RefreshCw className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
                {isRefreshing ? '爬取中...(约2分钟)' : '立即刷新'}
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
                  <span className="text-sm text-gray-600">条新闻</span>
                </div>
                {activeSource === 'all' && filteredNews && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-600">来源：</span>
                    <div className="flex flex-wrap gap-1">
                      {Array.from(new Set(filteredNews.map(n => n.source))).map(source => (
                        <Badge key={source} variant="outline" className="text-xs">
                          <span className="mr-0.5">{NEWS_SOURCES.find(s => s.key === source)?.icon}</span>
                          {NEWS_SOURCES.find(s => s.key === source)?.name}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="text-xs text-gray-500">
                {activeFilter !== 'all' && `已筛选：${activeFilter === 'pending' ? '待分析' : activeFilter === 'positive' ? '利好' : activeFilter === 'negative' ? '利空' : '中性'}`}
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
            <p className="mt-4">加载中...</p>
          </div>
        ) : filteredNews && filteredNews.length > 0 ? (
          filteredNews.map((news) => (
            <Card 
              key={news.id} 
              className={getCardStyle(news.sentiment_score)}
            >
              <CardHeader className="pb-2 flex-shrink-0">
                <CardTitle className="text-base leading-tight font-semibold text-gray-900 line-clamp-2 mb-1.5 min-h-[44px]">
                  {news.title}
                </CardTitle>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <div className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    <span>{formatRelativeTime(news.publish_time || news.created_at)}</span>
                  </div>
                  <span>•</span>
                  <div className="flex items-center gap-1">
                    <span>{NEWS_SOURCES.find(s => s.key === news.source)?.icon || '📰'}</span>
                    <span>{NEWS_SOURCES.find(s => s.key === news.source)?.name || news.source}</span>
                  </div>
                </div>
              </CardHeader>
              
              <CardContent className="flex-1 flex flex-col pb-3 pt-2 overflow-hidden">
                <p 
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
                  {news.content}
                </p>
                
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
                              收起 ({news.stock_codes.length} 只股票)
                            </>
                          ) : (
                            <>
                              <ChevronDown className="w-3 h-3" />
                              展开更多 ({news.stock_codes.length - 6} 只)
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
                      分析中...
                    </>
                  ) : news.sentiment_score !== null ? (
                    <>
                      <RefreshCcw className="w-4 h-4 mr-2" />
                      重新分析
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4 mr-2" />
                      分析
                    </>
                  )}
                </Button>
              </CardFooter>
            </Card>
          ))
        ) : (
          <div className="col-span-full text-center py-16">
            <div className="text-gray-400 mb-2">
              <Newspaper className="w-16 h-16 mx-auto opacity-50" />
            </div>
            <p className="text-gray-500 text-lg">暂无新闻</p>
            <p className="text-gray-400 text-sm mt-1">请先爬取新闻</p>
          </div>
        )}
      </div>
    </div>
  )
}

