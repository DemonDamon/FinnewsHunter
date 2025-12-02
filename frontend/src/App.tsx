import { Routes, Route } from 'react-router-dom'
import { Toaster } from 'sonner'
import MainLayout from './layout/MainLayout'
import Dashboard from './pages/Dashboard'
import NewsListPage from './pages/NewsListPage'
import StockAnalysisPage from './pages/StockAnalysisPage'
import AgentMonitorPage from './pages/AgentMonitorPage'
import TaskManagerPage from './pages/TaskManagerPage'

function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="news" element={<NewsListPage />} />
          <Route path="stock/:code" element={<StockAnalysisPage />} />
          <Route path="agents" element={<AgentMonitorPage />} />
          <Route path="tasks" element={<TaskManagerPage />} />
        </Route>
      </Routes>
      <Toaster richColors position="top-right" />
    </>
  )
}

export default App

