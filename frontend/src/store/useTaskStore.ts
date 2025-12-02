import { create } from 'zustand'
import type { CrawlTask, TaskStats } from '@/types/api'

interface TaskStore {
  tasks: CrawlTask[]
  taskStats: TaskStats | null
  setTasks: (tasks: CrawlTask[]) => void
  setTaskStats: (stats: TaskStats) => void
  addTask: (task: CrawlTask) => void
  updateTask: (taskId: number, updates: Partial<CrawlTask>) => void
}

export const useTaskStore = create<TaskStore>((set) => ({
  tasks: [],
  taskStats: null,
  
  setTasks: (tasks) => set({ tasks }),
  
  setTaskStats: (stats) => set({ taskStats: stats }),
  
  addTask: (task) =>
    set((state) => ({
      tasks: [task, ...state.tasks],
    })),
  
  updateTask: (taskId, updates) =>
    set((state) => ({
      tasks: state.tasks.map((task) =>
        task.id === taskId ? { ...task, ...updates } : task
      ),
    })),
}))

