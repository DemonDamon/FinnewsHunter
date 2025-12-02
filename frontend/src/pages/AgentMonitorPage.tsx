import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function AgentMonitorPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">智能体监控台</h1>
        <p className="text-muted-foreground">实时查看智能体执行状态</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>功能开发中...</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500">
            Phase 2 将实现智能体监控功能，包括：
          </p>
          <ul className="list-disc list-inside mt-2 text-gray-600 space-y-1">
            <li>智能体执行日志</li>
            <li>思考链可视化（Chain of Thought）</li>
            <li>工具调用追踪</li>
            <li>性能指标监控</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

