import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { taskApi } from '@/lib/api-client'
import { formatRelativeTime } from '@/lib/utils'

export default function TaskManagerPage() {
  const { data: tasks, isLoading } = useQuery({
    queryKey: ['tasks', 'list'],
    queryFn: () => taskApi.getTaskList({ limit: 20 }),
    refetchInterval: 5000, // 每5秒刷新
  })

  const getStatusBadge = (status: string) => {
    const variants = {
      completed: 'success' as const,
      running: 'default' as const,
      pending: 'secondary' as const,
      failed: 'destructive' as const,
    }
    const labels = {
      completed: '✅ 已完成',
      running: '⏳ 运行中',
      pending: '⏸️ 待执行',
      failed: '❌ 失败',
    }
    return <Badge variant={variants[status as keyof typeof variants] || 'outline'}>{labels[status as keyof typeof labels] || status}</Badge>
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">任务管理</h1>
        <p className="text-muted-foreground">爬取任务监控和管理</p>
      </div>

      <div className="space-y-4">
        {isLoading ? (
          <div className="text-center py-12 text-gray-500">加载中...</div>
        ) : tasks && tasks.length > 0 ? (
          tasks.map((task) => (
            <Card key={task.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">
                    任务 #{task.id} - {task.source}
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {getStatusBadge(task.status)}
                    <Badge variant="outline">{task.mode === 'realtime' ? '⚡ 实时' : '🥶 冷启动'}</Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <div className="text-gray-500">爬取数</div>
                    <div className="font-medium">{task.crawled_count}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">保存数</div>
                    <div className="font-medium">{task.saved_count}</div>
                  </div>
                  <div>
                    <div className="text-gray-500">耗时</div>
                    <div className="font-medium">
                      {task.execution_time ? `${task.execution_time.toFixed(2)}s` : '-'}
                    </div>
                  </div>
                  <div>
                    <div className="text-gray-500">创建时间</div>
                    <div className="font-medium">{formatRelativeTime(task.created_at)}</div>
                  </div>
                </div>

                {task.progress && task.progress.percentage && (
                  <div className="mt-4">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>进度</span>
                      <span>{task.progress.percentage}%</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-blue-600 h-2 rounded-full transition-all"
                        style={{ width: `${task.progress.percentage}%` }}
                      />
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))
        ) : (
          <div className="text-center py-12 text-gray-500">
            暂无任务记录
          </div>
        )}
      </div>
    </div>
  )
}

