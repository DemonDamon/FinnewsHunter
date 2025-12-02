import { create } from 'zustand'
import type { News } from '@/types/api'

interface NewsStore {
  newsList: News[]
  selectedNews: News | null
  setNewsList: (news: News[]) => void
  setSelectedNews: (news: News | null) => void
  updateNews: (newsId: number, updates: Partial<News>) => void
}

export const useNewsStore = create<NewsStore>((set) => ({
  newsList: [],
  selectedNews: null,
  
  setNewsList: (news) => set({ newsList: news }),
  
  setSelectedNews: (news) => set({ selectedNews: news }),
  
  updateNews: (newsId, updates) =>
    set((state) => ({
      newsList: state.newsList.map((news) =>
        news.id === newsId ? { ...news, ...updates } : news
      ),
    })),
}))

