import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { newsApi, taskApi } from '@/lib/api-client'
import { TrendingUp, Newspaper, Activity, Clock } from 'lucide-react'

export default function Dashboard() {
  const { data: newsList } = useQuery({
    queryKey: ['news', 'recent'],
    queryFn: () => newsApi.getNewsList({ limit: 5 }),
  })

  const { data: taskStats } = useQuery({
    queryKey: ['tasks', 'stats'],
    queryFn: () => taskApi.getTaskStats(),
    refetchInterval: 10000, // 每10秒刷新
  })

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
              每5分钟自动爬取
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 最新新闻 */}
      <Card>
        <CardHeader>
          <CardTitle>最新新闻</CardTitle>
          <CardDescription>最近爬取的新闻动态</CardDescription>
        </CardHeader>
        <CardContent>
          {newsList && newsList.length > 0 ? (
            <div className="space-y-4">
              {newsList.map((news) => (
                <div key={news.id} className="flex items-start gap-4 p-4 hover:bg-gray-50 rounded-lg transition-colors">
                  <div className="flex-1">
                    <h3 className="font-medium leading-tight">{news.title}</h3>
                    <p className="text-sm text-gray-600 mt-1 line-clamp-2">
                      {news.content}
                    </p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      <span>📰 {news.source}</span>
                      <span>⏰ {news.publish_time || news.created_at}</span>
                      {news.stock_codes && news.stock_codes.length > 0 && (
                        <span>📈 {news.stock_codes.join(', ')}</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              暂无新闻数据，请先爬取新闻
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

