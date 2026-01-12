import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { newsApi, taskApi } from '@/lib/api-client'
import { TrendingUp, Newspaper, Activity, Clock } from 'lucide-react'
import { useState, useMemo, useEffect } from 'react'
import { formatRelativeTime } from '@/lib/utils'
import NewsDetailDrawer from '@/components/NewsDetailDrawer'
import { useGlobalI18n, useLanguageStore } from '@/store/useLanguageStore'
import { useCallback } from 'react'

// 新闻源配置
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
  '同花顺财经': 'tonghuashun',
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

export default function Dashboard() {
  const t = useGlobalI18n()
  const { lang } = useLanguageStore()
  const [selectedSource, setSelectedSource] = useState<string>('all')
  const [selectedNewsId, setSelectedNewsId] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

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

  const { data: newsList } = useQuery({
    queryKey: ['news', 'dashboard', selectedSource],
    queryFn: () => newsApi.getLatestNews({ 
      source: selectedSource === 'all' ? undefined : selectedSource, 
      limit: 100
    }),
  })

  const { data: taskStats } = useQuery({
    queryKey: ['tasks', 'stats'],
    queryFn: () => taskApi.getTaskStats(),
    refetchInterval: 10000, // 每10秒刷新
  })

  // 按来源统计新闻数量
  const newsStats = useMemo(() => {
    if (!newsList) return []
    const stats = new Map<string, number>()
    newsList.forEach(news => {
      stats.set(news.source, (stats.get(news.source) || 0) + 1)
    })
    return Array.from(stats.entries()).map(([source, count]) => ({
      source,
      count,
      name: getSourceName(source),
      icon: getSourceIcon(source)
    })).sort((a, b) => b.count - a.count)
  }, [newsList, getSourceName, getSourceIcon])

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t.dashboard.title}</h1>
          <p className="text-muted-foreground">
            {t.dashboard.subtitle}
          </p>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t.dashboard.totalNews}
            </CardTitle>
            <Newspaper className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{taskStats?.total_news_saved || 0}</div>
            <p className="text-xs text-muted-foreground">
              {t.dashboard.savedToDb}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t.dashboard.totalTasks}
            </CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{taskStats?.total || 0}</div>
            <p className="text-xs text-muted-foreground">
              {t.dashboard.recentCompleted} {taskStats?.recent_completed || 0} {t.dashboard.units}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t.dashboard.crawlRate}
            </CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {taskStats && taskStats.total > 0
                ? (((taskStats.by_status?.completed || 0) / taskStats.total) * 100).toFixed(1)
                : '0.0'}%
            </div>
            <p className="text-xs text-muted-foreground">
              {taskStats?.by_status?.completed || 0} / {taskStats?.total || 0}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {t.dashboard.liveMonitor}
            </CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{t.dashboard.running}</div>
            <p className="text-xs text-muted-foreground">
              {t.dashboard.autoInterval}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 来源统计 */}
      {newsStats.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t.dashboard.newsStats}</CardTitle>
            <CardDescription>{t.dashboard.newsStatsDesc}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {newsStats.map(stat => (
                <Card key={stat.source} className="p-4 hover:shadow-md transition-shadow">
                  <div className="flex flex-col items-center gap-2">
                    <span className="text-3xl">{stat.icon}</span>
                    <span className="text-sm font-medium text-center">{stat.name}</span>
                    <span className="text-2xl font-bold text-blue-600">{stat.count}</span>
                  </div>
                </Card>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 来源筛选 */}
      <Card>
        <CardHeader>
          <CardTitle>{t.dashboard.latestNews}</CardTitle>
          <CardDescription>{t.dashboard.latestNewsDesc}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 筛选器 */}
          <div className="flex flex-wrap gap-2 p-3 bg-slate-50 rounded-lg">
            {NEWS_SOURCES.map(source => (
              <Button
                key={source.key}
                variant={selectedSource === source.key ? 'default' : 'outline'}
                size="sm"
                onClick={() => setSelectedSource(source.key)}
                className="text-xs"
              >
                <span className="mr-1">{source.icon}</span>
                {getSourceName(source.key)}
                {source.key !== 'all' && newsStats.find(s => s.source === source.key) && (
                  <Badge variant="secondary" className="ml-2">
                    {newsStats.find(s => s.source === source.key)?.count}
                  </Badge>
                )}
              </Button>
            ))}
          </div>

          {/* 新闻列表 */}
          {newsList && newsList.length > 0 ? (
            <div className="space-y-3 max-h-[600px] overflow-y-auto">
              {newsList.slice(0, 20).map((news) => (
                <div 
                  key={news.id} 
                  className="flex items-start gap-4 p-4 hover:bg-gray-50 rounded-lg transition-colors border border-gray-100 cursor-pointer"
                  onClick={() => {
                    setSelectedNewsId(news.id)
                    setDrawerOpen(true)
                  }}
                >
                  <div className="flex-1">
                    <h3 className="font-medium leading-tight">{news.title}</h3>
                    <p className="text-sm text-gray-600 mt-1 line-clamp-2">
                      {news.content}
                    </p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        <span>{getSourceIcon(news.source)}</span>
                        <span>{getSourceName(news.source)}</span>
                      </span>
                      <span>⏰ {formatRelativeTime(news.publish_time || news.created_at, t.time)}</span>
                      {news.stock_codes && news.stock_codes.length > 0 && (
                        <span className="flex items-center gap-1">
                          📈 
                          {news.stock_codes.slice(0, 3).map(code => (
                            <Badge key={code} variant="outline" className="text-xs">
                              {code}
                            </Badge>
                          ))}
                          {news.stock_codes.length > 3 && (
                            <span className="text-xs text-gray-400">
                              +{news.stock_codes.length - 3}
                            </span>
                          )}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              {selectedSource === 'all' ? t.dashboard.noNews : t.dashboard.noNewsFrom}
            </div>
          )}
        </CardContent>
      </Card>

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
