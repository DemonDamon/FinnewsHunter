/**
 * 辩论模式配置组件
 * 支持选择不同的多智能体协作模式
 */
import React, { useState, useEffect } from 'react'
import {
  Settings,
  Zap,
  Theater,
  Rocket,
  Clock,
  Users,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Info
} from 'lucide-react'
import { useGlobalI18n } from '@/store/useLanguageStore'

// 辩论模式类型
export interface DebateMode {
  id: string
  name: string
  description: string
  icon: string
  isDefault?: boolean
}

// 模式规则配置
export interface ModeRules {
  maxTime: number
  maxRounds?: number
  managerCanInterrupt?: boolean
  requireDataCollection?: boolean
}

// 可用的辩论模式（使用函数获取，支持国际化）
const getDebateModes = (t: any): DebateMode[] => [
  {
    id: 'parallel',
    name: t.stockDetail.parallelAnalysis,
    description: t.stockDetail.parallelAnalysisDesc || 'Bull/Bear parallel analysis, Investment Manager summarizes decision',
    icon: '⚡',
    isDefault: true
  },
  {
    id: 'realtime_debate',
    name: t.stockDetail.realtimeDebate,
    description: t.stockDetail.realtimeDebateDesc || 'Four agents real-time dialogue, Investment Manager moderates, Bull/Bear alternate',
    icon: '🎭'
  },
  {
    id: 'quick_analysis',
    name: t.stockDetail.quickAnalysis,
    description: t.stockDetail.quickAnalysisDesc || 'Single analyst quick recommendation, suitable for time-sensitive scenarios',
    icon: '🚀'
  }
]

// 默认规则配置
const DEFAULT_RULES: Record<string, ModeRules> = {
  parallel: {
    maxTime: 300,
    maxRounds: 1,
    managerCanInterrupt: false,
    requireDataCollection: false
  },
  realtime_debate: {
    maxTime: 600,
    maxRounds: 5,
    managerCanInterrupt: true,
    requireDataCollection: true
  },
  quick_analysis: {
    maxTime: 60,
    maxRounds: 1,
    managerCanInterrupt: false,
    requireDataCollection: false
  }
}

interface DebateConfigProps {
  selectedMode: string
  onModeChange: (mode: string) => void
  rules?: ModeRules
  onRulesChange?: (rules: ModeRules) => void
  disabled?: boolean
  compact?: boolean
}

export const DebateConfig: React.FC<DebateConfigProps> = ({
  selectedMode,
  onModeChange,
  rules,
  onRulesChange,
  disabled = false,
  compact = false
}) => {
  const t = useGlobalI18n()
  const DEBATE_MODES = getDebateModes(t)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [localRules, setLocalRules] = useState<ModeRules>(
    rules || DEFAULT_RULES[selectedMode] || DEFAULT_RULES.parallel
  )

  useEffect(() => {
    // 模式切换时重置规则为默认值
    setLocalRules(DEFAULT_RULES[selectedMode] || DEFAULT_RULES.parallel)
  }, [selectedMode])

  const handleRuleChange = (key: keyof ModeRules, value: number | boolean) => {
    const newRules = { ...localRules, [key]: value }
    setLocalRules(newRules)
    onRulesChange?.(newRules)
  }

  const getModeIcon = (mode: DebateMode) => {
    switch (mode.id) {
      case 'parallel':
        return <Zap className="w-5 h-5 text-yellow-500" />
      case 'realtime_debate':
        return <Theater className="w-5 h-5 text-purple-500" />
      case 'quick_analysis':
        return <Rocket className="w-5 h-5 text-blue-500" />
      default:
        return <Settings className="w-5 h-5 text-gray-500" />
    }
  }

  const selectedModeData = DEBATE_MODES.find(m => m.id === selectedMode)

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <label className="text-sm text-gray-500">{t.stockDetail.analysisMode}:</label>
        <select
          value={selectedMode}
          onChange={(e) => onModeChange(e.target.value)}
          disabled={disabled}
          className="text-sm border border-gray-200 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
        >
          {DEBATE_MODES.map((mode) => (
            <option key={mode.id} value={mode.id}>
              {mode.icon} {mode.name}
            </option>
          ))}
        </select>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* 模式选择 */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-3">
          <Settings className="w-5 h-5 text-gray-600" />
          <h3 className="font-semibold text-gray-800">{t.stockDetail.analysisModeConfig || t.stockDetail.analysisMode}</h3>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {DEBATE_MODES.map((mode) => (
            <button
              key={mode.id}
              onClick={() => onModeChange(mode.id)}
              disabled={disabled}
              className={`
                relative p-4 rounded-lg border-2 transition-all text-left
                ${selectedMode === mode.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }
                ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
              `}
            >
              {mode.isDefault && (
                <span className="absolute top-2 right-2 text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">
                  {t.stockDetail.default || 'Default'}
                </span>
              )}
              <div className="flex items-center gap-2 mb-2">
                {getModeIcon(mode)}
                <span className="font-medium text-gray-800">{mode.name}</span>
              </div>
              <p className="text-xs text-gray-500 line-clamp-2">
                {mode.description}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* 模式说明 */}
      {selectedModeData && (
        <div className="p-4 bg-gray-50 border-b border-gray-100">
          <div className="flex items-start gap-3">
            <div className="p-2 bg-white rounded-lg shadow-sm">
              {getModeIcon(selectedModeData)}
            </div>
            <div className="flex-1">
              <h4 className="font-medium text-gray-800 mb-1">
                {selectedModeData.name}
              </h4>
              <p className="text-sm text-gray-600">
                {selectedModeData.description}
              </p>
              
              {/* 模式特性标签 */}
              <div className="flex flex-wrap gap-2 mt-3">
                {selectedMode === 'parallel' && (
                  <>
                    <span className="inline-flex items-center gap-1 text-xs bg-yellow-100 text-yellow-700 px-2 py-1 rounded-full">
                      <Zap className="w-3 h-3" /> {t.stockDetail.parallelExecution || 'Parallel Execution'}
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                      <Clock className="w-3 h-3" /> {t.stockDetail.about2to3min || '~2-3 min'}
                    </span>
                  </>
                )}
                {selectedMode === 'realtime_debate' && (
                  <>
                    <span className="inline-flex items-center gap-1 text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded-full">
                      <MessageSquare className="w-3 h-3" /> {t.stockDetail.realtimeDialogue || 'Real-time Dialogue'}
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs bg-orange-100 text-orange-700 px-2 py-1 rounded-full">
                      <Users className="w-3 h-3" /> {t.stockDetail.fourAgents || '4 Agents'}
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                      <Clock className="w-3 h-3" /> {t.stockDetail.about5to10min || '~5-10 min'}
                    </span>
                  </>
                )}
                {selectedMode === 'quick_analysis' && (
                  <>
                    <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                      <Rocket className="w-3 h-3" /> {t.stockDetail.singleAgent || 'Single Agent'}
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                      <Clock className="w-3 h-3" /> {t.stockDetail.about1min || '~1 min'}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 高级配置 */}
      <div className="border-t border-gray-100">
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          disabled={disabled}
          className="w-full p-3 flex items-center justify-between text-sm text-gray-600 hover:bg-gray-50 transition-colors disabled:cursor-not-allowed"
        >
          <span className="flex items-center gap-2">
            <Info className="w-4 h-4" />
            {t.stockDetail.advancedConfig || 'Advanced Config'}
          </span>
          {showAdvanced ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </button>

        {showAdvanced && (
          <div className="p-4 border-t border-gray-100 bg-gray-50 space-y-4">
            {/* 最大时间 */}
            <div className="flex items-center justify-between">
              <label className="text-sm text-gray-600">{t.stockDetail.maxExecutionTime || 'Max Execution Time'}</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={localRules.maxTime}
                  onChange={(e) => handleRuleChange('maxTime', parseInt(e.target.value) || 300)}
                  disabled={disabled}
                  min={60}
                  max={1800}
                  step={60}
                  className="w-20 text-sm border border-gray-200 rounded px-2 py-1 text-right disabled:bg-gray-100"
                />
                <span className="text-sm text-gray-500">{t.stockDetail.seconds || 's'}</span>
              </div>
            </div>

            {/* 实时辩论模式专属配置 */}
            {selectedMode === 'realtime_debate' && (
              <>
                <div className="flex items-center justify-between">
                  <label className="text-sm text-gray-600">{t.stockDetail.maxDebateRounds || 'Max Debate Rounds'}</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      value={localRules.maxRounds || 5}
                      onChange={(e) => handleRuleChange('maxRounds', parseInt(e.target.value) || 5)}
                      disabled={disabled}
                      min={1}
                      max={10}
                      className="w-20 text-sm border border-gray-200 rounded px-2 py-1 text-right disabled:bg-gray-100"
                    />
                    <span className="text-sm text-gray-500">{t.stockDetail.rounds || 'rounds'}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <label className="text-sm text-gray-600">{t.stockDetail.managerCanInterrupt || 'Manager Can Interrupt'}</label>
                  <input
                    type="checkbox"
                    checked={localRules.managerCanInterrupt || false}
                    onChange={(e) => handleRuleChange('managerCanInterrupt', e.target.checked)}
                    disabled={disabled}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 disabled:cursor-not-allowed"
                  />
                </div>

                <div className="flex items-center justify-between">
                  <label className="text-sm text-gray-600">{t.stockDetail.collectDataBeforeDebate || 'Collect Data Before Debate'}</label>
                  <input
                    type="checkbox"
                    checked={localRules.requireDataCollection || false}
                    onChange={(e) => handleRuleChange('requireDataCollection', e.target.checked)}
                    disabled={disabled}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 disabled:cursor-not-allowed"
                  />
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// 辩论模式选择器（简化版本，用于其他页面）
export const DebateModeSelector: React.FC<{
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}> = ({ value, onChange, disabled }) => {
  const t = useGlobalI18n()
  const DEBATE_MODES = getDebateModes(t)
  return (
    <div className="flex gap-2">
      {DEBATE_MODES.map((mode) => (
        <button
          key={mode.id}
          onClick={() => onChange(mode.id)}
          disabled={disabled}
          className={`
            px-3 py-1.5 rounded-lg text-sm font-medium transition-all
            ${value === mode.id
              ? 'bg-blue-100 text-blue-700 border border-blue-300'
              : 'bg-gray-100 text-gray-600 border border-transparent hover:bg-gray-200'
            }
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
          title={mode.description}
        >
          <span className="mr-1">{mode.icon}</span>
          {mode.name}
        </button>
      ))}
    </div>
  )
}

export default DebateConfig

