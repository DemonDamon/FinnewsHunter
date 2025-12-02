import { useParams } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function StockAnalysisPage() {
  const { code } = useParams<{ code: string }>()

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">个股分析</h1>
        <p className="text-muted-foreground">股票代码: {code}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>功能开发中...</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500">
            Phase 2 将实现完整的个股分析功能，包括：
          </p>
          <ul className="list-disc list-inside mt-2 text-gray-600 space-y-1">
            <li>K线图展示</li>
            <li>新闻情感趋势</li>
            <li>关联新闻列表</li>
            <li>Bull vs Bear 辩论</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

