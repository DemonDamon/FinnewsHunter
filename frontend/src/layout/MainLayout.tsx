import { Outlet, Link, useLocation } from 'react-router-dom'
import { Home, Newspaper, TrendingUp, Activity, Settings, Brain } from 'lucide-react'
import { cn } from '@/lib/utils'
import ModelSelector from '@/components/ModelSelector'
import { NewsToolbarProvider, useNewsToolbar } from '@/context/NewsToolbarContext'
import { useLanguageStore, useGlobalI18n } from '@/store/useLanguageStore'

const navigationConfig = [
  { key: 'home', href: '/', icon: Home },
  { key: 'news', href: '/news', icon: Newspaper },
  { key: 'stock', href: '/stock', icon: TrendingUp },
  { key: 'alphaMining', href: '/alpha-mining', icon: Brain },
  { key: 'agents', href: '/agents', icon: Activity },
  { key: 'tasks', href: '/tasks', icon: Settings },
]

export default function MainLayout() {
  return (
    <NewsToolbarProvider>
      <MainLayoutInner />
    </NewsToolbarProvider>
  )
}

function MainLayoutInner() {
  const location = useLocation()
  const { content } = useNewsToolbar()
  const { lang, setLang } = useLanguageStore()
  const t = useGlobalI18n()
  
  const isNewsPage =
    location.pathname === '/news' || location.pathname.startsWith('/news/')

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
          {navigationConfig.map((item) => {
            const Icon = item.icon
            const name = t.nav[item.key as keyof typeof t.nav]
            const isActive = location.pathname === item.href ||
              (item.href !== '/' && location.pathname.startsWith(item.href))

            return (
              <Link
                key={item.key}
                to={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-700 hover:bg-gray-100'
                )}
              >
                <Icon className="w-5 h-5" />
                {name}
              </Link>
            )
          })}
        </nav>

        {/* 底部信息 */}
        <div className="p-4 border-t border-gray-200">
          <div className="text-xs text-gray-500">
            {t.header.poweredBy} <span className="font-semibold">AgenticX</span>
          </div>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 顶部栏 */}
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 gap-4">
          {/* 左侧：搜索框或标题 */}
          <div className="flex-1 max-w-xl">
            {isNewsPage ? (
              content.left || <h1 className="text-xl font-semibold text-gray-900">
                {lang === 'zh' ? '实时新闻流' : 'Real-time News Feed'}
              </h1>
            ) : (
              <h1 className="text-xl font-semibold text-gray-900">{t.header.title}</h1>
            )}
          </div>
          
          {/* 右侧：工具栏 */}
          <div className="flex items-center gap-4">
            {/* 语言切换 */}
            <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => setLang('en')}
                className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  lang === 'en' 
                    ? 'bg-white text-gray-900 shadow-sm' 
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                EN
              </button>
              <button
                onClick={() => setLang('zh')}
                className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  lang === 'zh' 
                    ? 'bg-white text-gray-900 shadow-sm' 
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                中文
              </button>
            </div>
            
            <ModelSelector />
            {isNewsPage && content.right}
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
