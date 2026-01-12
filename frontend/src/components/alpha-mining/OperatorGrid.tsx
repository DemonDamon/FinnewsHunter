/**
 * DSL 操作符可视化组件
 * 
 * 展示 21 个因子操作符，按类别分组显示
 * 支持点击插入到因子表达式输入框
 */

import React, { useState } from 'react';
import { Card } from '../ui/card';
import { Badge } from '../ui/badge';
import { motion } from 'framer-motion';
import { 
  Plus, Minus, X, Divide,
  ArrowRight, Clock, BarChart2,
  GitBranch, Maximize, Minimize,
  Activity, Zap, TrendingUp
} from 'lucide-react';
import { useGlobalI18n } from '@/store/useLanguageStore';

// 操作符分类
type OperatorCategory = 'arithmetic' | 'unary' | 'timeseries' | 'conditional' | 'special';

interface Operator {
  name: string;
  arity: number;
  description: string;
  category: OperatorCategory;
  example: string;
  icon: React.ReactNode;
}

// 获取操作符图标组件类型
type IconComponent = React.ComponentType<{ className?: string }>;

// 操作符图标组件映射
const OPERATOR_ICON_COMPONENTS: Record<string, IconComponent> = {
  ADD: Plus,
  SUB: Minus,
  MUL: X,
  DIV: Divide,
  NEG: Minus,
  ABS: Activity,
  SIGN: ArrowRight,
  GATE: GitBranch,
  MAX: Maximize,
  MIN: Minimize,
  DELAY1: Clock,
  DELAY5: Clock,
  DELTA1: TrendingUp,
  DELTA5: TrendingUp,
  MA5: BarChart2,
  MA10: BarChart2,
  STD5: Activity,
  STD10: Activity,
  JUMP: Zap,
  DECAY: TrendingUp,
  MAX3: Maximize,
};

// 获取操作符图标
const getOperatorIcon = (name: string): React.ReactNode => {
  const IconComponent = OPERATOR_ICON_COMPONENTS[name] || Activity;
  return <IconComponent className="w-4 h-4" />;
};

// 获取操作符定义（支持国际化）
const getOperators = (t: any): Operator[] => [
  // 算术运算 (4)
  { name: 'ADD', arity: 2, description: t.alphaMining.operators.add, category: 'arithmetic', example: 'ADD(x, y) = x + y', icon: getOperatorIcon('ADD') },
  { name: 'SUB', arity: 2, description: t.alphaMining.operators.sub, category: 'arithmetic', example: 'SUB(x, y) = x - y', icon: getOperatorIcon('SUB') },
  { name: 'MUL', arity: 2, description: t.alphaMining.operators.mul, category: 'arithmetic', example: 'MUL(x, y) = x × y', icon: getOperatorIcon('MUL') },
  { name: 'DIV', arity: 2, description: t.alphaMining.operators.div, category: 'arithmetic', example: 'DIV(x, y) = x / (y + ε)', icon: getOperatorIcon('DIV') },
  
  // 一元运算 (3)
  { name: 'NEG', arity: 1, description: t.alphaMining.operators.neg, category: 'unary', example: 'NEG(x) = -x', icon: getOperatorIcon('NEG') },
  { name: 'ABS', arity: 1, description: t.alphaMining.operators.abs, category: 'unary', example: 'ABS(x) = |x|', icon: getOperatorIcon('ABS') },
  { name: 'SIGN', arity: 1, description: t.alphaMining.operators.sign, category: 'unary', example: 'SIGN(x) = ±1 or 0', icon: getOperatorIcon('SIGN') },
  
  // 条件运算 (3)
  { name: 'GATE', arity: 3, description: t.alphaMining.operators.gate, category: 'conditional', example: 'GATE(c,x,y) = c>0?x:y', icon: getOperatorIcon('GATE') },
  { name: 'MAX', arity: 2, description: t.alphaMining.operators.max, category: 'conditional', example: 'MAX(x, y)', icon: getOperatorIcon('MAX') },
  { name: 'MIN', arity: 2, description: t.alphaMining.operators.min, category: 'conditional', example: 'MIN(x, y)', icon: getOperatorIcon('MIN') },
  
  // 时序运算 (8)
  { name: 'DELAY1', arity: 1, description: t.alphaMining.operators.delay1, category: 'timeseries', example: 'x[t-1]', icon: getOperatorIcon('DELAY1') },
  { name: 'DELAY5', arity: 1, description: t.alphaMining.operators.delay5, category: 'timeseries', example: 'x[t-5]', icon: getOperatorIcon('DELAY5') },
  { name: 'DELTA1', arity: 1, description: t.alphaMining.operators.delta1, category: 'timeseries', example: 'x[t] - x[t-1]', icon: getOperatorIcon('DELTA1') },
  { name: 'DELTA5', arity: 1, description: t.alphaMining.operators.delta5, category: 'timeseries', example: 'x[t] - x[t-5]', icon: getOperatorIcon('DELTA5') },
  { name: 'MA5', arity: 1, description: t.alphaMining.operators.ma5, category: 'timeseries', example: 'mean(x[t-4:t])', icon: getOperatorIcon('MA5') },
  { name: 'MA10', arity: 1, description: t.alphaMining.operators.ma10, category: 'timeseries', example: 'mean(x[t-9:t])', icon: getOperatorIcon('MA10') },
  { name: 'STD5', arity: 1, description: t.alphaMining.operators.std5, category: 'timeseries', example: 'std(x[t-4:t])', icon: getOperatorIcon('STD5') },
  { name: 'STD10', arity: 1, description: t.alphaMining.operators.std10, category: 'timeseries', example: 'std(x[t-9:t])', icon: getOperatorIcon('STD10') },
  
  // 特殊运算 (3)
  { name: 'JUMP', arity: 1, description: t.alphaMining.operators.jump, category: 'special', example: t.alphaMining.operators.jumpExample, icon: getOperatorIcon('JUMP') },
  { name: 'DECAY', arity: 1, description: t.alphaMining.operators.decay, category: 'special', example: 'x+0.8x[-1]+0.6x[-2]', icon: getOperatorIcon('DECAY') },
  { name: 'MAX3', arity: 1, description: t.alphaMining.operators.max3, category: 'special', example: 'max(x[t:t-2])', icon: getOperatorIcon('MAX3') },
];

// 特征列表
const FEATURES = ['RET', 'VOL', 'VOLUME_CHG', 'TURNOVER', 'SENTIMENT', 'NEWS_COUNT'];

// 获取类别配置（支持国际化）
const getCategoryConfig = (t: any): Record<OperatorCategory, { label: string; color: string; bgColor: string }> => ({
  arithmetic: { label: t.alphaMining.operators.categoryArithmetic, color: 'text-blue-600', bgColor: 'bg-blue-50 hover:bg-blue-100' },
  unary: { label: t.alphaMining.operators.categoryUnary, color: 'text-purple-600', bgColor: 'bg-purple-50 hover:bg-purple-100' },
  timeseries: { label: t.alphaMining.operators.categoryTimeseries, color: 'text-emerald-600', bgColor: 'bg-emerald-50 hover:bg-emerald-100' },
  conditional: { label: t.alphaMining.operators.categoryConditional, color: 'text-amber-600', bgColor: 'bg-amber-50 hover:bg-amber-100' },
  special: { label: t.alphaMining.operators.categorySpecial, color: 'text-rose-600', bgColor: 'bg-rose-50 hover:bg-rose-100' },
});

interface OperatorGridProps {
  onOperatorClick?: (operator: string) => void;
  onFeatureClick?: (feature: string) => void;
  compact?: boolean;
}

const OperatorGrid: React.FC<OperatorGridProps> = ({
  onOperatorClick,
  onFeatureClick,
  compact = false,
}) => {
  const t = useGlobalI18n();
  const OPERATORS = getOperators(t);
  const CATEGORY_CONFIG = getCategoryConfig(t);
  const [selectedCategory, setSelectedCategory] = useState<OperatorCategory | 'all'>('all');
  const [hoveredOp, setHoveredOp] = useState<string | null>(null);

  // 按类别过滤
  const filteredOperators = selectedCategory === 'all' 
    ? OPERATORS 
    : OPERATORS.filter(op => op.category === selectedCategory);

  // 按类别分组
  const groupedOperators = filteredOperators.reduce((acc, op) => {
    if (!acc[op.category]) acc[op.category] = [];
    acc[op.category].push(op);
    return acc;
  }, {} as Record<OperatorCategory, Operator[]>);

  return (
    <div className="space-y-4">
      {/* 类别筛选 */}
      <div className="flex flex-wrap gap-2">
        <Badge
          variant={selectedCategory === 'all' ? 'default' : 'outline'}
          className="cursor-pointer"
          onClick={() => setSelectedCategory('all')}
        >
          {t.alphaMining.operators.all} ({OPERATORS.length})
        </Badge>
        {(Object.entries(CATEGORY_CONFIG) as [OperatorCategory, typeof CATEGORY_CONFIG.arithmetic][]).map(([key, config]) => (
          <Badge
            key={key}
            variant={selectedCategory === key ? 'default' : 'outline'}
            className={`cursor-pointer ${selectedCategory === key ? '' : config.color}`}
            onClick={() => setSelectedCategory(key)}
          >
            {config.label} ({OPERATORS.filter(o => o.category === key).length})
          </Badge>
        ))}
      </div>

      {/* 特征列表 */}
      <Card className="p-3">
        <h4 className="text-sm font-medium text-gray-700 mb-2">{t.alphaMining.operators.availableFeatures}</h4>
        <div className="flex flex-wrap gap-2">
          {FEATURES.map((feature, idx) => (
            <motion.button
              key={feature}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className={`px-3 py-1.5 rounded-md text-sm font-mono transition-colors ${
                idx < 4 
                  ? 'bg-blue-100 text-blue-700 hover:bg-blue-200' 
                  : 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
              }`}
              onClick={() => onFeatureClick?.(feature)}
              title={idx < 4 ? t.alphaMining.operators.techFeature : t.alphaMining.operators.sentimentFeature}
            >
              {feature}
            </motion.button>
          ))}
        </div>
      </Card>

      {/* 操作符网格 */}
      {selectedCategory === 'all' ? (
        // 分组显示
        Object.entries(groupedOperators).map(([category, ops]) => (
          <div key={category}>
            <h4 className={`text-sm font-medium mb-2 ${CATEGORY_CONFIG[category as OperatorCategory].color}`}>
              {CATEGORY_CONFIG[category as OperatorCategory].label}
            </h4>
            <div className={`grid gap-2 ${compact ? 'grid-cols-4 md:grid-cols-6' : 'grid-cols-2 md:grid-cols-4'}`}>
              {ops.map((op) => (
                <OperatorCard
                  key={op.name}
                  operator={op}
                  compact={compact}
                  isHovered={hoveredOp === op.name}
                  onHover={() => setHoveredOp(op.name)}
                  onLeave={() => setHoveredOp(null)}
                  onClick={() => onOperatorClick?.(op.name)}
                />
              ))}
            </div>
          </div>
        ))
      ) : (
        // 单一类别
        <div className={`grid gap-2 ${compact ? 'grid-cols-4 md:grid-cols-6' : 'grid-cols-2 md:grid-cols-4'}`}>
          {filteredOperators.map((op) => (
            <OperatorCard
              key={op.name}
              operator={op}
              compact={compact}
              isHovered={hoveredOp === op.name}
              onHover={() => setHoveredOp(op.name)}
              onLeave={() => setHoveredOp(null)}
              onClick={() => onOperatorClick?.(op.name)}
            />
          ))}
        </div>
      )}

      {/* 操作符总数统计 */}
      <div className="text-xs text-gray-500 text-center">
        {t.alphaMining.operators.totalOperators.replace('{count}', String(OPERATORS.length))} · {t.alphaMining.operators.totalFeatures.replace('{count}', String(FEATURES.length))}
      </div>
    </div>
  );
};

// 单个操作符卡片
interface OperatorCardProps {
  operator: Operator;
  compact?: boolean;
  isHovered: boolean;
  onHover: () => void;
  onLeave: () => void;
  onClick: () => void;
}

const OperatorCard: React.FC<OperatorCardProps> = ({
  operator,
  compact,
  isHovered,
  onHover,
  onLeave,
  onClick,
}) => {
  const t = useGlobalI18n();
  const CATEGORY_CONFIG = getCategoryConfig(t);
  const config = CATEGORY_CONFIG[operator.category];

  return (
    <motion.div
      whileHover={{ scale: 1.02, y: -2 }}
      whileTap={{ scale: 0.98 }}
      className={`
        ${config.bgColor} 
        rounded-lg cursor-pointer transition-all duration-200
        ${isHovered ? 'shadow-md ring-2 ring-offset-1' : ''}
        ${compact ? 'p-2' : 'p-3'}
      `}
      style={{ 
        '--tw-ring-color': isHovered ? config.color.replace('text-', 'rgb(var(--') + ')' : undefined 
      } as React.CSSProperties}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      onClick={onClick}
    >
      <div className="flex items-center gap-2">
        <span className={config.color}>{operator.icon}</span>
        <span className={`font-mono font-semibold ${compact ? 'text-xs' : 'text-sm'} ${config.color}`}>
          {operator.name}
        </span>
        {!compact && (
          <Badge variant="secondary" className="text-xs ml-auto">
            {operator.arity}{t.alphaMining.operators.params}
          </Badge>
        )}
      </div>
      
      {!compact && (
        <>
          <p className="text-xs text-gray-600 mt-1">{operator.description}</p>
          <code className="text-xs text-gray-500 mt-1 block truncate" title={operator.example}>
            {operator.example}
          </code>
        </>
      )}
    </motion.div>
  );
};

export default OperatorGrid;
export { FEATURES };
export type { Operator, OperatorCategory };
