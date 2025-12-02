# FinnewsHunter Frontend (React + TypeScript)

现代化的金融新闻智能分析平台前端，基于 **React 18 + TypeScript + Vite + Tailwind CSS + Shadcn UI**。

## 技术栈

- **Core**: React 18, TypeScript, Vite
- **UI**: Tailwind CSS, Shadcn UI (Radix Primitives)
- **State**: Zustand, TanStack Query (React Query)
- **Routing**: React Router v6
- **Icons**: Lucide React
- **Notifications**: Sonner

## 快速开始

### 安装依赖

```bash
npm install
# 或使用 pnpm/yarn
```

### 开发模式

```bash
npm run dev
# 访问 http://localhost:3000
```

### 构建生产版本

```bash
npm run build
npm run preview
```

## 项目结构

```
src/
├── components/
│   └── ui/              # Shadcn UI 组件
│       ├── button.tsx
│       ├── card.tsx
│       └── badge.tsx
├── layout/
│   └── MainLayout.tsx   # 主布局（侧边栏+顶部栏）
├── pages/
│   ├── Dashboard.tsx            # 首页仪表盘
│   ├── NewsListPage.tsx         # 新闻流
│   ├── StockAnalysisPage.tsx    # 个股分析（待实现）
│   ├── AgentMonitorPage.tsx     # 智能体监控（待实现）
│   └── TaskManagerPage.tsx      # 任务管理
├── lib/
│   ├── api-client.ts    # API 客户端
│   └── utils.ts         # 工具函数
├── store/
│   ├── useNewsStore.ts  # 新闻状态
│   └── useTaskStore.ts  # 任务状态
├── types/
│   └── api.ts           # TypeScript 类型定义
├── App.tsx
├── main.tsx
└── index.css
```

## 功能特性

### ✅ 已实现
- Dashboard 仪表盘（统计卡片）
- 新闻列表展示
- 新闻爬取功能
- 智能分析按钮
- 任务管理列表
- 响应式布局
- 实时数据刷新（React Query）

### 🚧 开发中
- 个股深度分析
- K线图展示
- 智能体监控台
- WebSocket 实时推送
- 辩论可视化

## 开发指南

### 添加新组件

```bash
# 从 Shadcn UI 添加组件
npx shadcn-ui@latest add dialog
npx shadcn-ui@latest add tabs
```

### API 调用

```typescript
import { newsApi } from '@/lib/api-client'
import { useQuery } from '@tanstack/react-query'

const { data, isLoading } = useQuery({
  queryKey: ['news', 'list'],
  queryFn: () => newsApi.getNewsList({ limit: 20 }),
})
```

### 状态管理

```typescript
import { useNewsStore } from '@/store/useNewsStore'

const { newsList, setNewsList } = useNewsStore()
```

## 环境变量

创建 `.env.local` 文件：

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## 与后端集成

确保后端服务运行在 `http://localhost:8000`，前端会自动代理 API 请求到后端。

## 下一步

- [ ] 实现 WebSocket 连接（实时新闻推送）
- [ ] 实现个股分析页面（K线图）
- [ ] 实现智能体监控台（Chain of Thought）
- [ ] 实现辩论可视化（Bull vs Bear）

---

**Built with ❤️ using React + AgenticX**

