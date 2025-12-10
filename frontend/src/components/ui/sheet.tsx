import * as React from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

interface SheetContextValue {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const SheetContext = React.createContext<SheetContextValue | undefined>(undefined)

const Sheet = ({ 
  open, 
  onOpenChange, 
  children 
}: { 
  open: boolean
  onOpenChange: (open: boolean) => void
  children: React.ReactNode 
}) => {
  React.useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onOpenChange(false)
      }
    }
    if (open) {
      document.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [open, onOpenChange])

  return (
    <SheetContext.Provider value={{ open, onOpenChange }}>
      {children}
    </SheetContext.Provider>
  )
}

const SheetOverlay = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const context = React.useContext(SheetContext)
  if (!context) return null
  
  if (!context.open) return null

  return (
    <div
      ref={ref}
      className={cn(
        "fixed inset-0 z-50 bg-black/50 transition-opacity",
        context.open ? "opacity-100" : "opacity-0",
        className
      )}
      onClick={() => context.onOpenChange(false)}
      {...props}
    />
  )
})
SheetOverlay.displayName = "SheetOverlay"

interface SheetContentProps extends React.HTMLAttributes<HTMLDivElement> {
  side?: "top" | "bottom" | "left" | "right"
}

const SheetContent = React.forwardRef<
  HTMLDivElement,
  SheetContentProps
>(({ side = "right", className, children, ...props }, ref) => {
  const context = React.useContext(SheetContext)
  if (!context) return null

  // 使用状态来控制渲染，确保关闭动画能播放
  const [isVisible, setIsVisible] = React.useState(context.open)

  React.useEffect(() => {
    if (context.open) {
      setIsVisible(true)
    } else {
      // 延迟隐藏，让关闭动画播放
      const timer = setTimeout(() => setIsVisible(false), 300)
      return () => clearTimeout(timer)
    }
  }, [context.open])

  if (!isVisible) return null

  return (
    <>
      <SheetOverlay />
      <div
        ref={ref}
        className={cn(
          "fixed z-50 gap-4 bg-white p-6 shadow-lg transition-transform duration-300 ease-in-out",
          side === "right" && "inset-y-0 right-0 h-full w-full border-l sm:w-3/4 sm:max-w-2xl lg:max-w-4xl",
          side === "left" && "inset-y-0 left-0 h-full w-full border-r sm:w-3/4 sm:max-w-sm",
          side === "top" && "inset-x-0 top-0 border-b",
          side === "bottom" && "inset-x-0 bottom-0 border-t",
          className
        )}
        style={{
          transform: context.open 
            ? "translateX(0)" 
            : side === "right" 
              ? "translateX(100%)" 
              : side === "left" 
                ? "translateX(-100%)" 
                : "translateX(0)",
        }}
        {...props}
      >
        {children}
        <button
          onClick={() => context.onOpenChange(false)}
          className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-white transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-slate-950 focus:ring-offset-2 disabled:pointer-events-none"
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </button>
      </div>
    </>
  )
})
SheetContent.displayName = "SheetContent"

const SheetHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col space-y-2 text-center sm:text-left",
      className
    )}
    {...props}
  />
)
SheetHeader.displayName = "SheetHeader"

const SheetFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
      className
    )}
    {...props}
  />
)
SheetFooter.displayName = "SheetFooter"

const SheetTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h2
    ref={ref}
    className={cn("text-lg font-semibold text-slate-950", className)}
    {...props}
  />
))
SheetTitle.displayName = "SheetTitle"

const SheetDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-slate-500", className)}
    {...props}
  />
))
SheetDescription.displayName = "SheetDescription"

export {
  Sheet,
  SheetOverlay,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
}
