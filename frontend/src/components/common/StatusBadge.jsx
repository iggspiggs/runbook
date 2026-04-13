import React from 'react'
import { CheckCircle2, PauseCircle, Clock, Archive } from 'lucide-react'
import clsx from 'clsx'
import { twMerge } from 'tailwind-merge'

// Usage:
//   <StatusBadge status="active" />
//   <StatusBadge status="paused" size="sm" showIcon={false} />

const STATUS_CONFIG = {
  active: {
    label:     'Active',
    Icon:      CheckCircle2,
    className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  paused: {
    label:     'Paused',
    Icon:      PauseCircle,
    className: 'bg-amber-50 text-amber-600 border-amber-200',
  },
  planned: {
    label:     'Planned',
    Icon:      Clock,
    className: 'bg-sky-50 text-sky-600 border-sky-200',
  },
  deferred: {
    label:     'Deferred',
    Icon:      Archive,
    className: 'bg-slate-50 text-slate-400 border-slate-200',
  },
}

const SIZE_CLASSES = {
  xs: 'text-[9px] px-1 py-0 gap-0.5',
  sm: 'text-xs px-1.5 py-0.5 gap-1',
  md: 'text-xs px-2 py-0.5 gap-1.5',
  lg: 'text-sm px-2.5 py-1 gap-1.5',
}

const ICON_SIZE = {
  xs: 9,
  sm: 11,
  md: 12,
  lg: 13,
}

/**
 * StatusBadge — pill badge for rule lifecycle status.
 *
 * @param {Object} props
 * @param {'active'|'paused'|'planned'|'deferred'} props.status
 * @param {'sm'|'md'|'lg'} [props.size='md']
 * @param {boolean} [props.showIcon=true]
 * @param {boolean} [props.showLabel=true]
 * @param {string} [props.className]
 */
export default function StatusBadge({
  status,
  size = 'md',
  showIcon = true,
  showLabel = true,
  className,
}) {
  const normalized = status?.toLowerCase() ?? 'active'
  const config = STATUS_CONFIG[normalized] ?? STATUS_CONFIG.active
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
      aria-label={`Status: ${label}`}
    >
      {showIcon && (
        <Icon size={ICON_SIZE[size] ?? 12} aria-hidden="true" />
      )}
      {showLabel && label}
    </span>
  )
}
