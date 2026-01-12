import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ChevronDown, Check, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { llmApi } from '@/lib/api-client'
import { useGlobalI18n, useLanguageStore } from '@/store/useLanguageStore'

// 模型配置
export interface ModelConfig {
  provider: string
  model: string
}

// Provider 和 Model 的国际化映射
const PROVIDER_I18N: Record<string, { labelZh: string; labelEn: string }> = {
  bailian: {
    labelZh: '百炼（阿里云）',
    labelEn: 'Bailian (Alibaba Cloud)',
  },
  openai: {
    labelZh: 'OpenAI',
    labelEn: 'OpenAI',
  },
  deepseek: {
    labelZh: 'DeepSeek',
    labelEn: 'DeepSeek',
  },
  kimi: {
    labelZh: 'Kimi (Moonshot)',
    labelEn: 'Kimi (Moonshot)',
  },
  zhipu: {
    labelZh: '智谱',
    labelEn: 'Zhipu',
  },
}

const MODEL_DESCRIPTION_I18N: Record<string, { descZh: string; descEn: string }> = {
  bailian: {
    descZh: '百炼 模型',
    descEn: 'Bailian Model',
  },
  openai: {
    descZh: 'OpenAI 模型',
    descEn: 'OpenAI Model',
  },
  deepseek: {
    descZh: 'DeepSeek 模型',
    descEn: 'DeepSeek Model',
  },
  kimi: {
    descZh: 'Kimi 模型',
    descEn: 'Kimi Model',
  },
  zhipu: {
    descZh: '智谱 模型',
    descEn: 'Zhipu Model',
  },
}

const DEFAULT_CONFIG: ModelConfig = {
  provider: 'bailian',
  model: 'qwen-plus',
}

export default function ModelSelector() {
  const t = useGlobalI18n()
  const { lang } = useLanguageStore()
  const [config, setConfig] = useState<ModelConfig>(DEFAULT_CONFIG)
  
  // 从后端 API 动态加载可用厂商和模型
  const { data: llmConfig, isLoading } = useQuery({
    queryKey: ['llm-config'],
    queryFn: llmApi.getConfig,
    staleTime: 5 * 60 * 1000, // 缓存 5 分钟
    retry: 1,
  })
  
  // 国际化处理：将后端返回的 provider 和 model 数据转换为国际化文本
  const providers = useMemo(() => {
    if (!llmConfig?.providers) return []
    return llmConfig.providers.map(provider => {
      const providerI18n = PROVIDER_I18N[provider.value] || { 
        labelZh: provider.label, 
        labelEn: provider.label 
      }
      const modelDescI18n = MODEL_DESCRIPTION_I18N[provider.value] || { 
        descZh: `${provider.label} 模型`, 
        descEn: `${provider.label} Model` 
      }
      
      return {
        ...provider,
        label: lang === 'zh' ? providerI18n.labelZh : providerI18n.labelEn,
        models: provider.models.map(model => ({
          ...model,
          description: lang === 'zh' ? modelDescI18n.descZh : modelDescI18n.descEn,
        })),
      }
    })
  }, [llmConfig?.providers, lang])

  // 从 localStorage 加载配置
  useEffect(() => {
    const saved = localStorage.getItem('modelConfig')
    if (saved) {
      try {
        setConfig(JSON.parse(saved))
      } catch (e) {
        console.error('Failed to load model config:', e)
      }
    }
  }, [])

  // 保存配置到 localStorage
  const saveConfig = (newConfig: ModelConfig) => {
    setConfig(newConfig)
    localStorage.setItem('modelConfig', JSON.stringify(newConfig))
    // 触发全局事件，通知其他组件
    window.dispatchEvent(
      new CustomEvent('model-config-changed', { detail: newConfig })
    )
  }

  const currentProvider = providers.find((p) => p.value === config.provider)
  const currentModel = currentProvider?.models.find(
    (m) => m.value === config.model
  )

  // 加载状态
  if (isLoading) {
    return (
      <div className="flex items-center">
        <Button variant="outline" size="sm" disabled className="gap-2 h-10 rounded-lg px-3">
          <span className="text-sm">{t.model.loading}</span>
        </Button>
      </div>
    )
  }

  // 无可用厂商
  if (providers.length === 0) {
    return (
      <div className="flex items-center">
        <Button variant="outline" size="sm" disabled className="gap-2 h-10 rounded-lg px-3 border-orange-300">
          <AlertCircle className="h-4 w-4 text-orange-500" />
          <span className="text-sm text-orange-600">{t.model.notConfigured}</span>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex items-center">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="gap-2 h-10 rounded-lg px-3 border-slate-200 bg-white shadow-sm hover:shadow-md transition-all"
          >
            <span className="text-base">{currentProvider?.icon || '📦'}</span>
            <div className="flex flex-col items-start leading-tight">
              <span className="text-[11px] text-slate-500">
                {currentProvider?.label || t.model.selectModel}
              </span>
              <span className="text-sm font-semibold text-slate-900">
                {currentModel?.label || config.model}
              </span>
            </div>
            <ChevronDown className="h-4 w-4 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          className="w-96 max-h-[480px] overflow-y-auto border-slate-200 shadow-xl"
        >
          <DropdownMenuLabel className="text-xs text-slate-500">
            {t.model.selectTip}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />

          {providers.map((provider) => (
            <div key={provider.value} className="px-1 py-1">
              <DropdownMenuLabel className="text-xs text-slate-500 flex items-center gap-2">
                <span className="text-base">{provider.icon}</span>
                <span className="font-medium text-slate-700">{provider.label}</span>
                {!provider.has_api_key && (
                  <span className="text-xs text-orange-500 ml-auto">⚠️ {t.model.noApiKey}</span>
                )}
              </DropdownMenuLabel>
              <div className="grid gap-1">
                {provider.models.map((model) => {
                  const isActive =
                    config.provider === provider.value &&
                    config.model === model.value
                  return (
                    <DropdownMenuItem
                      key={`${provider.value}-${model.value}`}
                      onClick={() =>
                        saveConfig({
                          provider: provider.value,
                          model: model.value,
                        })
                      }
                      disabled={!provider.has_api_key}
                      className={cn(
                        "flex items-start gap-3 rounded-lg border border-transparent px-3 py-3 transition-colors",
                        !provider.has_api_key && "opacity-50 cursor-not-allowed",
                        isActive
                          ? "border-primary/30 bg-primary/5"
                          : "hover:bg-slate-50"
                      )}
                    >
                      <div className="flex flex-1 flex-col">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm text-slate-900">
                            {model.label}
                          </span>
                          {isActive && <Check className="h-4 w-4 text-primary" />}
                        </div>
                        <span className="text-xs text-slate-500">
                          {model.description}
                        </span>
                      </div>
                    </DropdownMenuItem>
                  )
                })}
              </div>
              <DropdownMenuSeparator className="my-2" />
            </div>
          ))}

          <div className="px-3 py-2 text-xs text-slate-500 bg-slate-50 rounded-md mx-1">
            {t.model.current}：{currentProvider?.label} · {currentModel?.label}
          </div>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

// 导出 hook 供其他组件使用
export function useModelConfig() {
  const [config, setConfig] = useState<ModelConfig>(DEFAULT_CONFIG)

  useEffect(() => {
    // 加载配置
    const saved = localStorage.getItem('modelConfig')
    if (saved) {
      try {
        setConfig(JSON.parse(saved))
      } catch (e) {
        console.error('Failed to load model config:', e)
      }
    }

    // 监听配置变化
    const handleConfigChange = (e: CustomEvent<ModelConfig>) => {
      setConfig(e.detail)
    }

    window.addEventListener(
      'model-config-changed',
      handleConfigChange as EventListener
    )

    return () => {
      window.removeEventListener(
        'model-config-changed',
        handleConfigChange as EventListener
      )
    }
  }, [])

  return config
}

