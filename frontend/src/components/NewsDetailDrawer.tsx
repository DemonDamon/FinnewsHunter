import { useQuery } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { newsApi, analysisApi } from '@/lib/api-client'
import { formatRelativeTime } from '@/lib/utils'
import {
  ExternalLink,
  Share2,
  Calendar,
  TrendingUp,
  CheckCircle2,
  XCircle,
  MinusCircle,
  Sparkles,
  Copy,
  Check,
  FileText,
  Code,
} from 'lucide-react'

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

interface NewsDetailDrawerProps {
  newsId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function NewsDetailDrawer({
  newsId,
  open,
  onOpenChange,
}: NewsDetailDrawerProps) {
  const [analyzing, setAnalyzing] = useState(false)
  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [showRawHtml, setShowRawHtml] = useState(false)  // 是否显示原始 HTML

  // 清理HTML标签并转换为Markdown
  const cleanMarkdown = (text: string): string => {
    return text
      // 替换HTML换行标签为Markdown换行
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<br>/gi, '\n')
      // 移除其他HTML标签
      .replace(/<[^>]+>/g, '')
      // 清理多余空行
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  }

  // 复制功能
  const handleCopy = async (text: string, analysisId: number) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(analysisId)
      toast.success('已复制到剪贴板')
      setTimeout(() => setCopiedId(null), 2000)
    } catch (err) {
      toast.error('复制失败，请手动复制')
    }
  }

  // 获取新闻详情
  const { data: news, isLoading } = useQuery({
    queryKey: ['news', 'detail', newsId],
    queryFn: () => newsApi.getNewsDetail(newsId!),
    enabled: !!newsId && open,
  })

  // 获取分析结果（如果已分析）
  const { data: analyses, refetch: refetchAnalyses } = useQuery({
    queryKey: ['analysis', 'news', newsId],
    queryFn: () => analysisApi.getNewsAnalyses(newsId!),
    enabled: !!newsId && open,
    staleTime: 0,  // 立即过期，确保每次打开都获取最新数据
  })

  // 获取相关新闻（同来源的其他新闻）
  const { data: relatedNews } = useQuery({
    queryKey: ['news', 'related', newsId],
    queryFn: async () => {
      if (!news) return []
      const allNews = await newsApi.getLatestNews({ 
        source: news.source, 
        limit: 10 
      })
      // 排除当前新闻，返回前5条
      return allNews.filter(n => n.id !== newsId).slice(0, 5)
    },
    enabled: !!newsId && open && !!news,
  })

  // 获取原始 HTML（仅在点击"查看原始内容"时加载）
  const { data: htmlData, isLoading: htmlLoading } = useQuery({
    queryKey: ['news', 'html', newsId],
    queryFn: () => newsApi.getNewsHtml(newsId!),
    enabled: !!newsId && open && showRawHtml,
  })

  // 当切换到新新闻时，重置分析状态
  useEffect(() => {
    setAnalyzing(false)
  }, [newsId])

  // 处理分享
  const handleShare = async () => {
    if (!news) return
    const url = `${window.location.origin}/news/${news.id}`
    try {
      await navigator.clipboard.writeText(url)
      toast.success('链接已复制到剪贴板')
    } catch (err) {
      toast.error('复制失败，请手动复制')
    }
  }

  // 处理分析
  const handleAnalyze = async () => {
    if (!newsId) return
    setAnalyzing(true)
    try {
      const result = await analysisApi.analyzeNews(newsId)
      if (result.success) {
        toast.success('分析完成！')
        // 刷新分析数据（不重载整个页面）
        await refetchAnalyses()
      } else {
        toast.error(result.error || '分析失败')
      }
    } catch (error) {
      toast.error('分析失败，请稍后重试')
    } finally {
      setAnalyzing(false)
    }
  }

  // 获取情感标签
  const getSentimentBadge = (score: number | null) => {
    if (score === null) {
      return (
        <Badge variant="outline" className="bg-gray-50 text-gray-700">
          <span className="mr-1">😐</span>
          待分析
        </Badge>
      )
    }
    if (score > 0.1) {
      return (
        <Badge className="bg-emerald-100 text-emerald-700 border-emerald-300">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          利好 {score.toFixed(2)}
        </Badge>
      )
    }
    if (score < -0.1) {
      return (
        <Badge className="bg-rose-100 text-rose-700 border-rose-300">
          <XCircle className="w-3 h-3 mr-1" />
          利空 {score.toFixed(2)}
        </Badge>
      )
    }
    return (
      <Badge className="bg-slate-100 text-slate-700 border-slate-300">
        <MinusCircle className="w-3 h-3 mr-1" />
        中性 {score.toFixed(2)}
      </Badge>
    )
  }

  const sourceInfo = NEWS_SOURCES.find(s => s.key === news?.source)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-4"></div>
              <p className="text-gray-500">加载中...</p>
            </div>
          </div>
        ) : !news ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-500">新闻不存在</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* 头部区域 */}
            <SheetHeader>
              <SheetTitle className="text-2xl font-bold leading-tight pr-8">
                {news.title}
              </SheetTitle>
              <SheetDescription>
                <div className="flex items-center gap-4 text-sm text-gray-500 mt-2">
                  <div className="flex items-center gap-1">
                    <span>{sourceInfo?.icon || '📰'}</span>
                    <span>{sourceInfo?.name || news.source}</span>
                  </div>
                  <span>•</span>
                  <div className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    <span>{formatRelativeTime(news.publish_time || news.created_at)}</span>
                  </div>
                  {news.author && (
                    <>
                      <span>•</span>
                      <span>作者：{news.author}</span>
                    </>
                  )}
                </div>
              </SheetDescription>
            </SheetHeader>

            {/* 操作按钮栏 */}
            <div className="flex flex-wrap gap-2 pb-4 border-b">
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.open(news.url, '_blank')}
                className="flex items-center gap-2"
              >
                <ExternalLink className="w-4 h-4" />
                原文链接
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleShare}
                className="flex items-center gap-2"
              >
                <Share2 className="w-4 h-4" />
                分享
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleAnalyze}
                disabled={analyzing}
                className="flex items-center gap-2"
              >
                <Sparkles className={`w-4 h-4 ${analyzing ? 'animate-spin' : ''}`} />
                {analyzing ? '分析中...' : '分析'}
              </Button>
              <Button
                variant={showRawHtml ? "default" : "outline"}
                size="sm"
                onClick={() => setShowRawHtml(!showRawHtml)}
                className="flex items-center gap-2"
              >
                <Code className="w-4 h-4" />
                {showRawHtml ? '显示解析内容' : '查看原始内容'}
              </Button>
            </div>

            {/* 情感分析卡片 - 优先显示最新分析结果 */}
            {(() => {
              // 优先使用最新分析记录中的评分，否则使用 news 表中的评分
              const latestScore = analyses && analyses.length > 0 && analyses[0].sentiment_score !== null
                ? analyses[0].sentiment_score
                : news.sentiment_score;
              
              if (latestScore === null) return null;
              
              return (
                <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-semibold text-gray-900 mb-2">情感分析</h3>
                        <div className="flex items-center gap-2">
                          {getSentimentBadge(latestScore)}
                          <span className="text-sm text-gray-600">
                            评分：{latestScore.toFixed(3)}
                          </span>
                        </div>
                      </div>
                      {analyses && analyses.length > 0 && (
                        <div className="text-xs text-gray-500">
                          分析时间：{formatRelativeTime(analyses[0].created_at)}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })()}

            {/* 股票代码区域 */}
            {news.stock_codes && news.stock_codes.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4" />
                  关联股票
                </h3>
                <div className="flex flex-wrap gap-2">
                  {news.stock_codes.map((code) => (
                    <Badge
                      key={code}
                      variant="outline"
                      className="text-sm bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100 cursor-pointer px-3 py-1"
                    >
                      <TrendingUp className="w-3 h-3 mr-1" />
                      {code}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* 完整正文区域 */}
            <div>
              <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                {showRawHtml ? <Code className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                {showRawHtml ? '原始内容' : '正文内容'}
              </h3>
              
              {showRawHtml ? (
                // 原始 HTML 展示区域
                <div className="border rounded-lg overflow-hidden bg-white">
                  {htmlLoading ? (
                    <div className="p-8 text-center text-gray-500">
                      <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-2"></div>
                      加载原始内容中...
                    </div>
                  ) : htmlData?.raw_html ? (
                    <iframe
                      srcDoc={htmlData.raw_html}
                      className="w-full border-0"
                      style={{ height: '600px' }}
                      sandbox="allow-same-origin"
                      title="原始新闻内容"
                    />
                  ) : (
                    <div className="p-8 text-center text-gray-500">
                      <Code className="w-8 h-8 mx-auto mb-2 opacity-50" />
                      <p>该新闻暂无原始 HTML 内容</p>
                      <p className="text-sm mt-1">请重新爬取该新闻以获取完整内容</p>
                    </div>
                  )}
                </div>
              ) : (
                // 解析后的文本展示
                <div className="prose prose-sm max-w-none">
                  <div className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                    {news.content.split('\n').map((paragraph, idx) => (
                      <p key={idx} className="mb-4">
                        {paragraph}
                      </p>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* 分析详情 */}
            {analyses && analyses.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <Sparkles className="w-4 h-4" />
                  智能体分析详情
                </h3>
                {analyses.map((analysis) => {
                  // 清理和合并所有内容用于复制
                  const fullContent = [
                    analysis.summary ? `## 摘要\n\n${cleanMarkdown(analysis.summary)}` : '',
                    analysis.analysis_result ? `## 详细分析\n\n${cleanMarkdown(analysis.analysis_result)}` : ''
                  ].filter(Boolean).join('\n\n')

                  return (
                    <Card key={analysis.id} className="mb-4 relative">
                      <CardContent className="pt-6">
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <Badge variant="outline">{analysis.agent_name}</Badge>
                            <div className="flex items-center gap-2">
                              {analysis.confidence && (
                                <span className="text-xs text-gray-500">
                                  置信度：{(analysis.confidence * 100).toFixed(1)}%
                                </span>
                              )}
                            </div>
                          </div>
                          {analysis.summary && (
                            <div>
                              <h4 className="font-medium text-sm text-gray-700 mb-2">摘要</h4>
                              <div className="prose prose-sm max-w-none">
                                <ReactMarkdown
                                  remarkPlugins={[remarkGfm]}
                                  className="text-sm text-gray-600 leading-relaxed"
                                  components={{
                                    h1: ({node, ...props}) => <h1 className="text-base font-bold mb-2 mt-3" {...props} />,
                                    h2: ({node, ...props}) => <h2 className="text-sm font-bold mb-2 mt-2" {...props} />,
                                    h3: ({node, ...props}) => <h3 className="text-sm font-semibold mb-1 mt-2" {...props} />,
                                    h4: ({node, ...props}) => <h4 className="text-sm font-medium mb-1 mt-2" {...props} />,
                                    p: ({node, ...props}) => <p className="mb-2" {...props} />,
                                    ul: ({node, ...props}) => <ul className="list-disc list-inside mb-2 space-y-1" {...props} />,
                                    ol: ({node, ...props}) => <ol className="list-decimal list-inside mb-2 space-y-1" {...props} />,
                                    li: ({node, ...props}) => <li className="ml-2" {...props} />,
                                    strong: ({node, ...props}) => <strong className="font-semibold text-gray-800" {...props} />,
                                    em: ({node, ...props}) => <em className="italic" {...props} />,
                                    code: ({node, ...props}) => (
                                      <code className="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono text-gray-800" {...props} />
                                    ),
                                    pre: ({node, ...props}) => <pre className="bg-gray-100 p-2 rounded overflow-x-auto mb-2" {...props} />,
                                    blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-gray-300 pl-3 italic text-gray-600 my-2" {...props} />,
                                    hr: ({node, ...props}) => <hr className="my-3 border-gray-200" {...props} />,
                                    table: ({node, ...props}) => (
                                      <div className="overflow-x-auto my-3">
                                        <table className="min-w-full border-collapse border border-gray-300 text-xs" {...props} />
                                      </div>
                                    ),
                                    thead: ({node, ...props}) => <thead className="bg-gray-50" {...props} />,
                                    tbody: ({node, ...props}) => <tbody {...props} />,
                                    tr: ({node, ...props}) => <tr className="border-b border-gray-200" {...props} />,
                                    th: ({node, ...props}) => <th className="border border-gray-300 px-3 py-2 text-left font-semibold bg-gray-100" {...props} />,
                                    td: ({node, ...props}) => <td className="border border-gray-300 px-3 py-2" {...props} />,
                                  }}
                                >
                                  {cleanMarkdown(analysis.summary)}
                                </ReactMarkdown>
                              </div>
                            </div>
                          )}
                          {analysis.analysis_result && (
                            <div>
                              <h4 className="font-medium text-sm text-gray-700 mb-2">详细分析</h4>
                              <div className="prose prose-sm max-w-none">
                                <ReactMarkdown
                                  remarkPlugins={[remarkGfm]}
                                  className="text-sm text-gray-600 leading-relaxed"
                                  components={{
                                    h1: ({node, ...props}) => <h1 className="text-base font-bold mb-2 mt-3" {...props} />,
                                    h2: ({node, ...props}) => <h2 className="text-sm font-bold mb-2 mt-2" {...props} />,
                                    h3: ({node, ...props}) => <h3 className="text-sm font-semibold mb-1 mt-2" {...props} />,
                                    h4: ({node, ...props}) => <h4 className="text-sm font-medium mb-1 mt-2" {...props} />,
                                    p: ({node, ...props}) => <p className="mb-2" {...props} />,
                                    ul: ({node, ...props}) => <ul className="list-disc list-inside mb-2 space-y-1" {...props} />,
                                    ol: ({node, ...props}) => <ol className="list-decimal list-inside mb-2 space-y-1" {...props} />,
                                    li: ({node, ...props}) => <li className="ml-2" {...props} />,
                                    strong: ({node, ...props}) => <strong className="font-semibold text-gray-800" {...props} />,
                                    em: ({node, ...props}) => <em className="italic" {...props} />,
                                    code: ({node, ...props}) => (
                                      <code className="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono text-gray-800" {...props} />
                                    ),
                                    pre: ({node, ...props}) => <pre className="bg-gray-100 p-2 rounded overflow-x-auto mb-2" {...props} />,
                                    blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-gray-300 pl-3 italic text-gray-600 my-2" {...props} />,
                                    hr: ({node, ...props}) => <hr className="my-3 border-gray-200" {...props} />,
                                    table: ({node, ...props}) => (
                                      <div className="overflow-x-auto my-3">
                                        <table className="min-w-full border-collapse border border-gray-300 text-xs" {...props} />
                                      </div>
                                    ),
                                    thead: ({node, ...props}) => <thead className="bg-gray-50" {...props} />,
                                    tbody: ({node, ...props}) => <tbody {...props} />,
                                    tr: ({node, ...props}) => <tr className="border-b border-gray-200" {...props} />,
                                    th: ({node, ...props}) => <th className="border border-gray-300 px-3 py-2 text-left font-semibold bg-gray-100" {...props} />,
                                    td: ({node, ...props}) => <td className="border border-gray-300 px-3 py-2" {...props} />,
                                  }}
                                >
                                  {cleanMarkdown(analysis.analysis_result)}
                                </ReactMarkdown>
                              </div>
                            </div>
                          )}
                          <div className="flex items-center justify-between pt-2 border-t">
                            <span className="text-xs text-gray-400">
                              分析时间：{formatRelativeTime(analysis.created_at)}
                            </span>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleCopy(fullContent, analysis.id)}
                              className="h-7 px-2 text-xs"
                            >
                              {copiedId === analysis.id ? (
                                <>
                                  <Check className="w-3 h-3 mr-1" />
                                  已复制
                                </>
                              ) : (
                                <>
                                  <Copy className="w-3 h-3 mr-1" />
                                  复制
                                </>
                              )}
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            )}

            {/* 相关新闻推荐 */}
            {relatedNews && relatedNews.length > 0 && (
              <div>
                <h3 className="font-semibold text-gray-900 mb-3">相关新闻</h3>
                <div className="space-y-2">
                  {relatedNews.map((related) => (
                    <Card
                      key={related.id}
                      className="hover:shadow-md transition-shadow cursor-pointer"
                      onClick={() => {
                        onOpenChange(false)
                        setTimeout(() => {
                          // 触发父组件更新newsId
                          window.dispatchEvent(new CustomEvent('news-select', { detail: related.id }))
                        }, 300)
                      }}
                    >
                      <CardContent className="pt-4">
                        <h4 className="font-medium text-sm line-clamp-2 mb-2">
                          {related.title}
                        </h4>
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <span>{formatRelativeTime(related.publish_time || related.created_at)}</span>
                          {related.stock_codes && related.stock_codes.length > 0 && (
                            <>
                              <span>•</span>
                              <span>{related.stock_codes.length} 只股票</span>
                            </>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

