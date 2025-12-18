/**
 * KLineChart 组件
 * 使用 klinecharts 库展示专业的 K 线图
 * 支持：蜡烛图、成交量、MA均线、MACD等
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import { init, dispose, registerLocale } from 'klinecharts'
import type { Chart } from 'klinecharts'
import type { KLineDataPoint } from '@/types/api'
import { cn } from '@/lib/utils'

// 注册中文语言包
registerLocale('zh-CN', {
  time: '时间：',
  open: '开：',
  high: '高：',
  low: '低：',
  close: '收：',
  volume: '量：',
  turnover: '额：',
  change: '涨跌：',
})

interface KLineChartProps {
  data: KLineDataPoint[]
  height?: number
  className?: string
  showVolume?: boolean
  showMA?: boolean
  showMACD?: boolean
  theme?: 'light' | 'dark'
  period?: 'daily' | '1m' | '5m' | '15m' | '30m' | '60m'  // 添加周期参数
}

export default function KLineChart({
  data,
  height = 500,
  className,
  showVolume = true,
  showMA = true,
  showMACD = false,
  theme = 'light',
  period = 'daily',
}: KLineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<Chart | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)

  // 转换数据格式 - klinecharts 需要的格式
  const formatData = useCallback((rawData: KLineDataPoint[]) => {
    return rawData.map((item) => ({
      timestamp: item.timestamp,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
      volume: item.volume,
      turnover: item.turnover,
    }))
  }, [])

  // 初始化图表
  useEffect(() => {
    if (!containerRef.current) return

    // 销毁旧图表
    if (chartRef.current) {
      dispose(chartRef.current)
      chartRef.current = null
    }

    // 中国 A 股风格样式：红涨绿跌
    const styles = {
      grid: {
        show: true,
        horizontal: {
          show: true,
          size: 1,
          color: theme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
          style: 'dashed' as const,
        },
        vertical: {
          show: true,
          size: 1,
          color: theme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
          style: 'dashed' as const,
        },
      },
      candle: {
        type: 'candle_solid' as const,
        bar: {
          upColor: '#EF5350',      // 红色涨
          downColor: '#26A69A',    // 绿色跌
          noChangeColor: '#888888',
          upBorderColor: '#EF5350',
          downBorderColor: '#26A69A',
          noChangeBorderColor: '#888888',
          upWickColor: '#EF5350',
          downWickColor: '#26A69A',
          noChangeWickColor: '#888888',
        },
        priceMark: {
          show: true,
          high: {
            show: true,
            color: theme === 'dark' ? '#D9D9D9' : '#333333',
            textOffset: 5,
            textSize: 10,
            textFamily: 'Helvetica Neue',
            textWeight: 'normal',
          },
          low: {
            show: true,
            color: theme === 'dark' ? '#D9D9D9' : '#333333',
            textOffset: 5,
            textSize: 10,
            textFamily: 'Helvetica Neue',
            textWeight: 'normal',
          },
          last: {
            show: true,
            upColor: '#EF5350',
            downColor: '#26A69A',
            noChangeColor: '#888888',
            line: {
              show: true,
              style: 'dashed' as const,
              dashedValue: [4, 4],
              size: 1,
            },
            text: {
              show: true,
              style: 'fill' as const,
              size: 12,
              paddingLeft: 4,
              paddingTop: 4,
              paddingRight: 4,
              paddingBottom: 4,
              borderColor: 'transparent',
              borderSize: 0,
              borderRadius: 2,
              color: '#FFFFFF',
              family: 'Helvetica Neue',
              weight: 'normal',
            },
          },
        },
        tooltip: {
          showRule: 'always' as const,
          showType: 'standard' as const,
        },
      },
      indicator: {
        ohlc: {
          upColor: '#EF5350',
          downColor: '#26A69A',
          noChangeColor: '#888888',
        },
        bars: [
          {
            style: 'fill' as const,
            borderStyle: 'solid' as const,
            borderSize: 1,
            borderDashedValue: [2, 2],
            upColor: 'rgba(239, 83, 80, 0.7)',
            downColor: 'rgba(38, 166, 154, 0.7)',
            noChangeColor: '#888888',
          },
        ],
        lines: [
          { style: 'solid' as const, smooth: false, size: 1, dashedValue: [2, 2], color: '#FF9600' },
          { style: 'solid' as const, smooth: false, size: 1, dashedValue: [2, 2], color: '#9D65C9' },
          { style: 'solid' as const, smooth: false, size: 1, dashedValue: [2, 2], color: '#2196F3' },
          { style: 'solid' as const, smooth: false, size: 1, dashedValue: [2, 2], color: '#E91E63' },
          { style: 'solid' as const, smooth: false, size: 1, dashedValue: [2, 2], color: '#00BCD4' },
        ],
      },
      xAxis: {
        show: true,
        size: 'auto' as const,
        axisLine: {
          show: true,
          color: theme === 'dark' ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)',
          size: 1,
        },
        tickText: {
          show: true,
          color: theme === 'dark' ? '#D9D9D9' : '#666666',
          family: 'Helvetica Neue',
          weight: 'normal',
          size: 11,
        },
        tickLine: {
          show: true,
          size: 1,
          length: 3,
          color: theme === 'dark' ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)',
        },
      },
      yAxis: {
        show: true,
        size: 'auto' as const,
        position: 'right' as const,
        type: 'normal' as const,
        inside: false,
        reverse: false,
        axisLine: {
          show: true,
          color: theme === 'dark' ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)',
          size: 1,
        },
        tickText: {
          show: true,
          color: theme === 'dark' ? '#D9D9D9' : '#666666',
          family: 'Helvetica Neue',
          weight: 'normal',
          size: 11,
        },
        tickLine: {
          show: true,
          size: 1,
          length: 3,
          color: theme === 'dark' ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)',
        },
      },
      crosshair: {
        show: true,
        horizontal: {
          show: true,
          line: {
            show: true,
            style: 'dashed' as const,
            dashedValue: [4, 2],
            size: 1,
            color: theme === 'dark' ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.2)',
          },
          text: {
            show: true,
            style: 'fill' as const,
            color: '#FFFFFF',
            size: 12,
            family: 'Helvetica Neue',
            weight: 'normal',
            borderStyle: 'solid' as const,
            borderDashedValue: [2, 2],
            borderSize: 1,
            borderColor: theme === 'dark' ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)',
            borderRadius: 2,
            paddingLeft: 4,
            paddingRight: 4,
            paddingTop: 2,
            paddingBottom: 2,
            backgroundColor: theme === 'dark' ? 'rgba(35,35,35,0.95)' : 'rgba(50,50,50,0.9)',
          },
        },
        vertical: {
          show: true,
          line: {
            show: true,
            style: 'dashed' as const,
            dashedValue: [4, 2],
            size: 1,
            color: theme === 'dark' ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.2)',
          },
          text: {
            show: true,
            style: 'fill' as const,
            color: '#FFFFFF',
            size: 12,
            family: 'Helvetica Neue',
            weight: 'normal',
            borderStyle: 'solid' as const,
            borderDashedValue: [2, 2],
            borderSize: 1,
            borderColor: theme === 'dark' ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)',
            borderRadius: 2,
            paddingLeft: 4,
            paddingRight: 4,
            paddingTop: 2,
            paddingBottom: 2,
            backgroundColor: theme === 'dark' ? 'rgba(35,35,35,0.95)' : 'rgba(50,50,50,0.9)',
          },
        },
      },
    }

    // 创建图表
    const chart = init(containerRef.current, {
      locale: 'zh-CN',
      styles,
    })

    if (chart) {
      chartRef.current = chart
      
      // 设置自定义时间格式化
      chart.setCustomApi({
        formatDate: (dateTimeFormat: any, timestamp: number, format: string, type: number) => {
          const date = new Date(timestamp)
          
          // 日线：只显示日期
          if (period === 'daily') {
            const year = date.getFullYear()
            const month = String(date.getMonth() + 1).padStart(2, '0')
            const day = String(date.getDate()).padStart(2, '0')
            return `${month}-${day}`  // 简化为月-日
          }
          
          // 分钟线：显示月-日 时:分
          const month = String(date.getMonth() + 1).padStart(2, '0')
          const day = String(date.getDate()).padStart(2, '0')
          const hours = String(date.getHours()).padStart(2, '0')
          const minutes = String(date.getMinutes()).padStart(2, '0')
          return `${month}-${day} ${hours}:${minutes}`
        },
      })
      
      // 设置右侧留白为最小，让 K 线尽量占满
      chart.setOffsetRightDistance(20)
      
      // 先添加 MA 均线到主图（蜡烛图上叠加）
      if (showMA) {
        chart.createIndicator('MA', false, { id: 'candle_pane' })
      }

      // 添加成交量指标 - 在独立的副图面板
      if (showVolume) {
        chart.createIndicator('VOL')
      }

      // 添加 MACD 指标 - 在独立的副图面板
      if (showMACD) {
        chart.createIndicator('MACD')
      }

      setIsInitialized(true)
    }

    return () => {
      if (chartRef.current) {
        dispose(chartRef.current)
        chartRef.current = null
      }
    }
  }, [theme, showVolume, showMA, showMACD, period])

  // 更新数据
  useEffect(() => {
    if (!chartRef.current || !isInitialized || !data || data.length === 0) return

    const formattedData = formatData(data)
    chartRef.current.applyNewData(formattedData)
  }, [data, isInitialized, formatData])

  return (
    <div
      ref={containerRef}
      className={cn('w-full rounded-lg overflow-hidden bg-white', className)}
      style={{ height }}
    />
  )
}

// 简化版迷你 K 线图组件
export function MiniKLineChart({
  data,
  height = 150,
  className,
}: {
  data: KLineDataPoint[]
  height?: number
  className?: string
}) {
  return (
    <KLineChart
      data={data}
      height={height}
      className={className}
      showVolume={false}
      showMA={false}
      showMACD={false}
      theme="light"
    />
  )
}
