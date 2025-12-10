import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { newsApi, taskApi } from '@/lib/api-client'
import { TrendingUp, Newspaper, Activity, Clock } from 'lucide-react'
import { useState, useMemo, useEffect } from 'react'
import { formatRelativeTime } from '@/lib/utils'
import NewsDetailDrawer from '@/components/NewsDetailDrawer'

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

export default function Dashboard() {
  const [selectedSource, setSelectedSource] = useState<string>('all')
  const [selectedNewsId, setSelectedNewsId] = useState<number | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

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
      name: NEWS_SOURCES.find(s => s.key === source)?.name || source,
      icon: NEWS_SOURCES.find(s => s.key === source)?.icon || '📰'
    })).sort((a, b) => b.count - a.count)
  }, [newsList])

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">仪表盘</h1>
          <p className="text-muted-foreground">
            金融新闻智能分析平台 - Powered by AgenticX
          </p>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              总新闻数
            </CardTitle>
            <Newspaper className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{taskStats?.total_news_saved || 0}</div>
            <p className="text-xs text-muted-foreground">
              已保存到数据库
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              总任务数
            </CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{taskStats?.total || 0}</div>
            <p className="text-xs text-muted-foreground">
              最近完成 {taskStats?.recent_completed || 0} 个
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              爬取成功率
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
              实时监控
            </CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">运行中</div>
            <p className="text-xs text-muted-foreground">
              每1分钟自动爬取
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 来源统计 */}
      {newsStats.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>新闻来源统计</CardTitle>
            <CardDescription>各新闻源的内容数量分布</CardDescription>
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
          <CardTitle>最新新闻</CardTitle>
          <CardDescription>最近爬取的新闻动态</CardDescription>
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
                {source.name}
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
                        <span>{NEWS_SOURCES.find(s => s.key === news.source)?.icon}</span>
                        <span>{NEWS_SOURCES.find(s => s.key === news.source)?.name || news.source}</span>
                      </span>
                      <span>⏰ {formatRelativeTime(news.publish_time || news.created_at)}</span>
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
              {selectedSource === 'all' ? '暂无新闻数据，请先爬取新闻' : `暂无来自 ${NEWS_SOURCES.find(s => s.key === selectedSource)?.name} 的新闻`}
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
