import React from 'react'

interface HighlightTextProps {
  text: string
  highlight: string
  className?: string
}

/**
 * HighlightText 组件
 * 
 * 用于在文本中高亮显示指定的关键词
 * 
 * @param text - 原始文本
 * @param highlight - 需要高亮的关键词
 * @param className - 应用到容器的 CSS 类名
 * 
 * @example
 * <HighlightText 
 *   text="贵州茅台股价上涨" 
 *   highlight="茅台" 
 *   className="text-sm"
 * />
 */
export default function HighlightText({ text, highlight, className = '' }: HighlightTextProps) {
  // 如果没有高亮词，直接返回原文本
  if (!highlight || !highlight.trim()) {
    return <span className={className}>{text}</span>
  }

  // 转义特殊正则字符，避免正则表达式错误
  const escapeRegExp = (str: string) => {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  }

  try {
    // 使用正则表达式分割文本，保留匹配部分
    const escapedHighlight = escapeRegExp(highlight.trim())
    const parts = text.split(new RegExp(`(${escapedHighlight})`, 'gi'))

    return (
      <span className={className}>
        {parts.map((part, index) => {
          // 判断是否为匹配的关键词（不区分大小写）
          const isMatch = part.toLowerCase() === highlight.toLowerCase()
          
          return isMatch ? (
            <mark 
              key={index} 
              className="bg-yellow-200 text-gray-900 font-semibold px-0.5 rounded"
            >
              {part}
            </mark>
          ) : (
            <React.Fragment key={index}>{part}</React.Fragment>
          )
        })}
      </span>
    )
  } catch (error) {
    // 如果正则表达式出错，返回原文本
    console.error('HighlightText error:', error)
    return <span className={className}>{text}</span>
  }
}

