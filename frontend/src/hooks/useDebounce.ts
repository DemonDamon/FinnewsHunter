import { useState, useEffect } from 'react'

/**
 * useDebounce Hook
 * 
 * 用于延迟处理快速变化的值（如搜索输入），避免频繁触发计算或API请求
 * 
 * @param value - 需要防抖的值
 * @param delay - 延迟时间（毫秒），默认 500ms
 * @returns 防抖后的值
 * 
 * @example
 * const [searchTerm, setSearchTerm] = useState('')
 * const debouncedSearchTerm = useDebounce(searchTerm, 300)
 * 
 * useEffect(() => {
 *   // 只有当用户停止输入 300ms 后才会执行
 *   fetchSearchResults(debouncedSearchTerm)
 * }, [debouncedSearchTerm])
 */
export function useDebounce<T>(value: T, delay: number = 500): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    // 设置定时器，在delay后更新debouncedValue
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    // 清理函数：如果value在delay时间内再次变化，清除上一个定时器
    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])

  return debouncedValue
}

