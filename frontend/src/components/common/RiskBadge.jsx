import React from 'react'
import { AlertTriangle, AlertCircle, Info, Flame } from 'lucide-react'
import clsx from 'clsx'
import { twMerge } from 'tailwind-merge'

// Usage:
//   <RiskBadge level="critical" />
//   <RiskBadge level="low" size="sm" />
//   <RiskBadge level="high" showLabel={false} />

const RISK_CONFIG = {
  low: {
    label:      'Low',
    Icon:       Info,
    className:  'bg-emerald-50 text-emerald-600 border-emerald-200',
    dotClass:   'bg-emerald-300',
  },
  medium: {
    label:      'Medium',
    Icon:       AlertTriangle,
    className:  'bg-amber-50 text-amber-600 border-amber-200',
    dotClass:   'bg-amber-300',
  },
  high: {
    label:      'High',
    Icon:       AlertCircle,
    className:  'bg-orange-50 text-orange-600 border-orange-200',
    dotClass:   'bg-orange-400',
  },
  critical: {
    label:      'Critical',
    Icon:       Flame,
    className:  'bg-red-50 text-red-600 border-red-200',
    dotClass:   'bg-red-400',
  },
}

const SIZE_CLASSES = {
  xs:  'text-[9px] px-1 py-0 gap-0.5',
  sm:  'text-xs px-1.5 py-0.5 gap-1',
  md:  'text-xs px-2 py-0.5 gap-1.5',
  lg:  'text-sm px-2.5 py-1 gap-1.5',
}

const ICON_SIZE = {
  xs: 9,
  sm: 11,
  md: 12,
  lg: 13,
}

/**
 * RiskBadge — color-coded pill badge for rule risk levels.
 *
 * @param {Object} props
 * @param {'low'|'medium'|'high'|'critical'} props.level
 * @param {'sm'|'md'|'lg'} [props.size='md']
 * @param {boolean} [props.showLabel=true]
 * @param {boolean} [props.showIcon=true]
 * @param {string} [props.className]
 */
export default function RiskBadge({
  level,
  size = 'md',
  showLabel = true,
  showIcon = true,
  className,
}) {
  const normalized = level?.toLowerCase() ?? 'low'
  const config = RISK_CONFIG[normalized] ?? RISK_CONFIG.low
  const { label, Icon } = config

  return (
    <span
      className={twMerge(
        clsx(
          'inline-flex items-center font-medium rounded-full border',
          'leading-none whitespace-nowrap',
          config.className,
          SIZE_CLASSES[size] ?? SIZE_CLASSES.md
        ),
        className
      )}
      aria-label={`Risk level: ${label}`}
    >
      {showIcon && (
        <Icon size={ICON_SIZE[size] ?? 12} aria-hidden="true" />
      )}
      {showLabel && label}
    </span>
  )
}

/**
 * RiskDot — a simple colored circle, useful in dense table cells.
 */
export function RiskDot({ level, className }) {
  const normalized = level?.toLowerCase() ?? 'low'
  const config = RISK_CONFIG[normalized] ?? RISK_CONFIG.low

  return (
    <span
      className={twMerge(
        clsx('inline-block w-2 h-2 rounded-full flex-shrink-0', config.dotClass),
        className
      )}
      aria-label={`Risk: ${config.label}`}
      title={config.label}
    />
  )
}
