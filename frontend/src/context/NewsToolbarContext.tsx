import React, { createContext, useContext, useState } from 'react'

interface ToolbarContent {
  left?: React.ReactNode | null
  right?: React.ReactNode | null
}

interface NewsToolbarContextValue {
  content: ToolbarContent
  setContent: (content: ToolbarContent) => void
}

const NewsToolbarContext = createContext<NewsToolbarContextValue>({
  content: {},
  setContent: () => {},
})

export const NewsToolbarProvider = ({
  children,
}: {
  children: React.ReactNode
}) => {
  const [content, setContent] = useState<ToolbarContent>({})

  return (
    <NewsToolbarContext.Provider value={{ content, setContent }}>
      {children}
    </NewsToolbarContext.Provider>
  )
}

export const useNewsToolbar = () => useContext(NewsToolbarContext)


