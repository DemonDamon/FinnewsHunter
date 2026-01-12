import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d)
}

export interface TimeI18n {
  justNow: string
  minutesAgo: string
  hoursAgo: string
  daysAgo: string
}

const defaultTimeI18n: TimeI18n = {
  justNow: '刚刚',
  minutesAgo: '分钟前',
  hoursAgo: '小时前',
  daysAgo: '天前',
}

export function formatRelativeTime(date: string | Date, i18n?: TimeI18n): string {
  const t = i18n || defaultTimeI18n
  const d = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  
  if (diffMins < 1) return t.justNow
  if (diffMins < 60) return `${diffMins}${t.minutesAgo}`
  
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}${t.hoursAgo}`
  
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}${t.daysAgo}`
  
  return formatDate(d)
}

