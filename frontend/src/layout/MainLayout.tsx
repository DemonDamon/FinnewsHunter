import { Outlet, Link, useLocation } from 'react-router-dom'
import { Home, Newspaper, TrendingUp, Activity, Settings, Search } from 'lucide-react'
import { cn } from '@/lib/utils'

const navigation = [
  { name: '首页', href: '/', icon: Home },
  { name: '新闻流', href: '/news', icon: Newspaper },
  { name: '个股分析', href: '/stock/SH600519', icon: TrendingUp },
  { name: '智能体监控', href: '/agents', icon: Activity },
  { name: '任务管理', href: '/tasks', icon: Settings },
]

export default function MainLayout() {
  const location = useLocation()

  return (
    <div className="flex h-screen bg-gray-50">
      {/* 侧边栏 */}
      <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
        {/* Logo */}
        <div className="h-16 flex items-center px-6 border-b border-gray-200">
          <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            🎯 FinnewsHunter
          </h1>
        </div>

        {/* 导航 */}
        <nav className="flex-1 px-4 py-4 space-y-1">
          {navigation.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.href ||
              (item.href !== '/' && location.pathname.startsWith(item.href))

            return (
              <Link
                key={item.name}
                to={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-700 hover:bg-gray-100'
                )}
              >
                <Icon className="w-5 h-5" />
                {item.name}
              </Link>
            )
          })}
        </nav>

        {/* 底部信息 */}
        <div className="p-4 border-t border-gray-200">
          <div className="text-xs text-gray-500">
            Powered by <span className="font-semibold">AgenticX</span>
          </div>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 顶部栏 */}
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
          <div className="flex-1 max-w-2xl">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="搜索新闻、股票代码..."
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="text-sm text-gray-600">
              <span className="font-medium">LLM:</span> qwen-plus
            </div>
          </div>
        </header>

        {/* 页面内容 */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

