import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { newsApi, analysisApi } from '@/lib/api-client'
import { formatRelativeTime } from '@/lib/utils'
import { Download, RefreshCw, Sparkles } from 'lucide-react'
import type { News } from '@/types/api'

export default function NewsListPage() {
  const queryClient = useQueryClient()
  const [crawlPages, setCrawlPages] = useState({ start: 1, end: 1 })

  // 获取新闻列表
  const { data: newsList, isLoading, refetch } = useQuery({
    queryKey: ['news', 'list'],
    queryFn: () => newsApi.getNewsList({ limit: 50 }),
  })

  // 爬取新闻 mutation
  const crawlMutation = useMutation({
    mutationFn: newsApi.crawlNews,
    onSuccess: () => {
      toast.success('爬取任务已启动，请稍等10秒后刷新')
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['news'] })
      }, 10000)
    },
    onError: (error: Error) => {
      toast.error(`爬取失败: ${error.message}`)
    },
  })

  // 分析新闻 mutation
  const analyzeMutation = useMutation({
    mutationFn: analysisApi.analyzeNews,
    onSuccess: (data) => {
      if (data.success) {
        toast.success('分析完成！')
        queryClient.invalidateQueries({ queryKey: ['news'] })
      } else {
        toast.error(`分析失败: ${data.error}`)
      }
    },
    onError: (error: Error) => {
      toast.error(`分析失败: ${error.message}`)
    },
  })

  const handleCrawl = () => {
    crawlMutation.mutate({
      source: 'sina',
      start_page: crawlPages.start,
      end_page: crawlPages.end,
    })
  }

  const handleAnalyze = (newsId: number) => {
    analyzeMutation.mutate(newsId)
  }

  const getSentimentBadge = (score: number | null) => {
    if (score === null) return null
    if (score > 0.1) return <Badge variant="success">😊 利好 {score.toFixed(2)}</Badge>
    if (score < -0.1) return <Badge variant="destructive">😰 利空 {score.toFixed(2)}</Badge>
    return <Badge variant="outline">😐 中性 {score.toFixed(2)}</Badge>
  }

  return (
    <div className="p-6 space-y-6">
      {/* 操作栏 */}
      <Card>
        <CardHeader>
          <CardTitle>新闻爬取</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">起始页:</label>
              <input
                type="number"
                min="1"
                value={crawlPages.start}
                onChange={(e) => setCrawlPages({ ...crawlPages, start: Number(e.target.value) })}
                className="w-20 px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">结束页:</label>
              <input
                type="number"
                min="1"
                max="10"
                value={crawlPages.end}
                onChange={(e) => setCrawlPages({ ...crawlPages, end: Number(e.target.value) })}
                className="w-20 px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <Button
              onClick={handleCrawl}
              disabled={crawlMutation.isPending}
            >
              <Download className="w-4 h-4" />
              {crawlMutation.isPending ? '爬取中...' : '爬取新闻'}
            </Button>
            <Button
              onClick={() => refetch()}
              variant="outline"
            >
              <RefreshCw className="w-4 h-4" />
              刷新列表
            </Button>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            提示：页码1通常是最新新闻，建议从第1页开始爬取
          </p>
        </CardContent>
      </Card>

      {/* 新闻列表 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {isLoading ? (
          <div className="col-span-full text-center py-12 text-gray-500">
            加载中...
          </div>
        ) : newsList && newsList.length > 0 ? (
          newsList.map((news) => (
            <Card key={news.id} className="hover:shadow-lg transition-shadow">
              <CardHeader>
                <CardTitle className="text-base leading-tight">
                  {news.title}
                </CardTitle>
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <span>📅 {formatRelativeTime(news.publish_time || news.created_at)}</span>
                  <span>•</span>
                  <span>📰 {news.source}</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-gray-600 line-clamp-3">
                  {news.content}
                </p>
                
                {news.stock_codes && news.stock_codes.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {news.stock_codes.map((code) => (
                      <Badge key={code} variant="outline" className="text-xs">
                        📈 {code}
                      </Badge>
                    ))}
                  </div>
                )}

                {news.sentiment_score !== null && (
                  <div>{getSentimentBadge(news.sentiment_score)}</div>
                )}

                <Button
                  onClick={() => handleAnalyze(news.id)}
                  disabled={news.sentiment_score !== null || analyzeMutation.isPending}
                  size="sm"
                  className="w-full"
                >
                  <Sparkles className="w-4 h-4" />
                  {news.sentiment_score !== null ? '✓ 已分析' : '分析'}
                </Button>
              </CardContent>
            </Card>
          ))
        ) : (
          <div className="col-span-full text-center py-12 text-gray-500">
            暂无新闻，请先爬取新闻
          </div>
        )}
      </div>
    </div>
  )
}

