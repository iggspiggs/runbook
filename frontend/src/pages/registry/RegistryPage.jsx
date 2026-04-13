import React, { useEffect, useCallback, useState } from 'react'
import {
  Search, ChevronUp, ChevronDown, ChevronsUpDown,
  X, SlidersHorizontal, RefreshCw, CheckSquare,
} from 'lucide-react'
import clsx from 'clsx'
import useRegistryStore from '../../stores/registryStore.js'
import RiskBadge from '../../components/common/RiskBadge.jsx'
import StatusBadge from '../../components/common/StatusBadge.jsx'
import RuleDrawer from './RuleDrawer.jsx'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEPARTMENTS = ['Order Intake', 'Fulfillment', 'Shipping', 'Billing', 'Notifications', 'Analytics', 'Compliance']
const STATUSES    = ['active', 'paused', 'planned', 'deferred']
const RISK_LEVELS = ['low', 'medium', 'high', 'critical']

const COLUMNS = [
  { key: 'rule_id',      label: 'Rule ID',    sortable: true,  width: 'w-28' },
  { key: 'title',        label: 'Title',      sortable: true,  width: 'flex-1' },
  { key: 'department',   label: 'Dept',       sortable: true,  width: 'w-28' },
  { key: 'status',       label: 'Status',     sortable: true,  width: 'w-24' },
  { key: 'risk_level',   label: 'Risk',       sortable: true,  width: 'w-24' },
  { key: 'owner',        label: 'Owner',      sortable: true,  width: 'w-32' },
  { key: 'last_changed', label: 'Changed',    sortable: true,  width: 'w-28' },
  { key: 'verified',     label: 'Verified',   sortable: false, width: 'w-20' },
]

// ---------------------------------------------------------------------------
// Mock data (used when API is unavailable)
// ---------------------------------------------------------------------------
const MOCK_RULES = Array.from({ length: 24 }, (_, i) => {
  const depts     = DEPARTMENTS
  const statuses  = STATUSES
  const risks     = RISK_LEVELS
  const dept      = depts[i % depts.length]
  const prefix    = dept.slice(0, 3).toUpperCase()
  const padded    = String(i + 1).padStart(3, '0')
  return {
    rule_id:      `${prefix}-${padded}`,
    title:        `${dept} automation rule #${i + 1}`,
    department:   dept,
    status:       statuses[i % statuses.length],
    risk_level:   risks[i % risks.length],
    owner:        ['alice@co.com', 'bob@co.com', 'carol@co.com', 'system'][i % 4],
    last_changed: new Date(Date.now() - i * 3_600_000 * 7).toISOString(),
    verified:     i % 3 !== 0,
  }
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(isoString) {
  if (!isoString) return '—'
  const diff = Date.now() - new Date(isoString).getTime()
  const days = Math.floor(diff / 86_400_000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(new Date(isoString))
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

function FilterBar({ filters, onUpdate, onClear, loading }) {
  const hasActiveFilters =
    filters.search || filters.department || filters.status ||
    filters.risk_level || filters.verified !== null

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Search */}
      <div className="relative flex-1 min-w-48">
        <Search
          size={14}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-slate-400"
        />
        <input
          type="text"
          placeholder="Search rules…"
          value={filters.search}
          onChange={e => onUpdate({ search: e.target.value })}
          className="
            w-full pl-8 pr-3 py-1.5 text-sm rounded-lg
            border border-slate-200 bg-white text-slate-900
            placeholder:text-slate-400
            focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-slate-400
            transition-shadow duration-150
          "
          aria-label="Search rules"
        />
      </div>

      {/* Department */}
      <select
        value={filters.department}
        onChange={e => onUpdate({ department: e.target.value })}
        className="select-field text-sm"
        aria-label="Filter by department"
      >
        <option value="">All departments</option>
        {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
      </select>

      {/* Status */}
      <select
        value={filters.status}
        onChange={e => onUpdate({ status: e.target.value })}
        className="select-field text-sm"
        aria-label="Filter by status"
      >
        <option value="">All statuses</option>
        {STATUSES.map(s => (
          <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
        ))}
      </select>

      {/* Risk level */}
      <select
        value={filters.risk_level}
        onChange={e => onUpdate({ risk_level: e.target.value })}
        className="select-field text-sm"
        aria-label="Filter by risk level"
      >
        <option value="">All risk levels</option>
        {RISK_LEVELS.map(r => (
          <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
        ))}
      </select>

      {/* Verified toggle */}
      <button
        onClick={() => onUpdate({
          verified: filters.verified === true ? false : filters.verified === false ? null : true,
        })}
        className={clsx(
          'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm border transition-colors',
          filters.verified === true  && 'bg-slate-100 border-slate-300 text-slate-700',
          filters.verified === false && 'bg-slate-100 border-slate-300 text-slate-500',
          filters.verified === null  && 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
        )}
        aria-label="Toggle verified filter"
      >
        <CheckSquare size={13} />
        {filters.verified === true  ? 'Verified' : filters.verified === false ? 'Unverified' : 'Verified?'}
      </button>

      {/* Clear */}
      {hasActiveFilters && (
        <button
          onClick={onClear}
          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm text-slate-500 hover:bg-slate-100 transition-colors"
          aria-label="Clear all filters"
        >
          <X size={13} />
          Clear
        </button>
      )}

      {loading && <RefreshCw size={13} className="text-slate-400 animate-spin ml-1" />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sort header cell
// ---------------------------------------------------------------------------

function SortHeader({ column, currentSort, currentDir, onSort }) {
  const active = currentSort === column.key
  return (
    <th
      scope="col"
      className={clsx(
        'px-3 py-2.5 text-left',
        column.width,
        column.sortable && 'cursor-pointer select-none hover:bg-slate-100 transition-colors'
      )}
      onClick={column.sortable ? () => onSort(column.key) : undefined}
      aria-sort={active ? (currentDir === 'asc' ? 'ascending' : 'descending') : undefined}
    >
      <div className="flex items-center gap-1 text-xs font-semibold text-slate-500 uppercase tracking-wide">
        {column.label}
        {column.sortable && (
          active
            ? currentDir === 'asc'
              ? <ChevronUp size={11} className="text-slate-400" />
              : <ChevronDown size={11} className="text-slate-400" />
            : <ChevronsUpDown size={11} className="text-slate-300" />
        )}
      </div>
    </th>
  )
}

// ---------------------------------------------------------------------------
// Department accent colors (used for pill border + drawer header strip)
// ---------------------------------------------------------------------------

function deptColor(_dept) {
  return '#a8a29e'
}

// ---------------------------------------------------------------------------
// Table row
// ---------------------------------------------------------------------------

function RuleRow({ rule, index, selected, onSelect }) {
  return (
    <tr
      className={clsx(
        'border-b border-slate-100 last:border-0 cursor-pointer transition-colors',
        selected ? 'bg-slate-50' : 'bg-white hover:bg-slate-50'
      )}
      onClick={() => onSelect(rule.rule_id)}
      aria-selected={selected}
    >
      {/* Rule ID */}
      <td className="px-3 py-3 w-28">
        <code
          className="font-mono text-xs text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded-md"
        >
          {rule.rule_id}
        </code>
      </td>

      {/* Title */}
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-800 truncate max-w-xs">
            {rule.title}
          </span>
          {!rule.verified && (
            <span
              className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-amber-400"
              title="Not yet verified"
              aria-label="Unverified"
            />
          )}
        </div>
      </td>

      {/* Department */}
      <td className="px-3 py-3 w-28">
        <span className="text-sm text-slate-600">{rule.department ?? '—'}</span>
      </td>

      {/* Status */}
      <td className="px-3 py-3 w-24">
        <StatusBadge status={rule.status} size="sm" />
      </td>

      {/* Risk */}
      <td className="px-3 py-3 w-24">
        <RiskBadge level={rule.risk_level} size="sm" />
      </td>

      {/* Owner */}
      <td className="px-3 py-3 w-32">
        <span className="text-xs text-slate-500 truncate block max-w-[120px]">
          {rule.owner ?? '—'}
        </span>
      </td>

      {/* Last changed */}
      <td className="px-3 py-3 w-28">
        <span className="text-xs text-slate-400">{timeAgo(rule.last_changed)}</span>
      </td>

      {/* Verified */}
      <td className="px-3 py-3 w-20">
        {rule.verified ? (
          <span className="text-slate-500" title="Verified" aria-label="Verified">
            <CheckSquare size={14} />
          </span>
        ) : (
          <span className="text-amber-400" title="Not verified" aria-label="Not verified">
            <CheckSquare size={14} className="opacity-30" />
          </span>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// RegistryPage
// ---------------------------------------------------------------------------

export default function RegistryPage() {
  const {
    rules, totalCount, filters, loading, selectedRule,
    fetchRules, selectRule, updateFilter, clearFilters, setSort,
  } = useRegistryStore()

  const [displayRules, setDisplayRules] = useState([])

  useEffect(() => {
    fetchRules().catch(() => {
      // On failure, show mock data
      setDisplayRules(MOCK_RULES)
    })
  }, [])

  // Use store rules if available, else fall back to mock
  useEffect(() => {
    if (rules.length > 0) {
      setDisplayRules(rules)
    } else if (!loading) {
      setDisplayRules(MOCK_RULES)
    }
  }, [rules, loading])

  const handleSort = useCallback((col) => {
    if (setSort) setSort(col)
  }, [setSort])

  const total = totalCount || displayRules.length

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-slate-200 bg-white space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Rules Registry</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {total.toLocaleString()} rule{total !== 1 ? 's' : ''}
              {filters.search && ` matching "${filters.search}"`}
            </p>
          </div>
          <button
            onClick={() => fetchRules()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        <FilterBar
          filters={filters}
          onUpdate={updateFilter}
          onClear={clearFilters}
          loading={loading}
        />
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto scrollbar-thin">
        <table className="w-full border-collapse min-w-[800px]">
          <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10 shadow-[0_1px_0_rgba(0,0,0,0.05)]">
            <tr>
              {COLUMNS.map(col => (
                <SortHeader
                  key={col.key}
                  column={col}
                  currentSort={filters.sort_by}
                  currentDir={filters.sort_dir}
                  onSort={handleSort}
                />
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-slate-50">
            {loading && displayRules.length === 0 ? (
              <tr>
                <td colSpan={COLUMNS.length} className="text-center py-16 text-slate-400 text-sm">
                  <RefreshCw size={20} className="animate-spin mx-auto mb-2" />
                  Loading rules…
                </td>
              </tr>
            ) : displayRules.length === 0 ? (
              <tr>
                <td colSpan={COLUMNS.length} className="text-center py-20">
                  <div className="flex flex-col items-center gap-3">
                    <SlidersHorizontal size={20} className="text-slate-300" />
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-slate-600">No rules match your filters</p>
                      <p className="text-xs text-slate-400">Try broadening your search or clearing filters</p>
                    </div>
                    <button
                      onClick={clearFilters}
                      className="mt-1 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 border border-slate-200 bg-white hover:bg-slate-50 transition-colors"
                    >
                      Clear all filters
                    </button>
                  </div>
                </td>
              </tr>
            ) : (
              displayRules.map((rule, index) => (
                <RuleRow
                  key={rule.rule_id}
                  rule={rule}
                  index={index}
                  selected={selectedRule?.rule_id === rule.rule_id}
                  onSelect={selectRule}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > filters.page_size && (
        <div className="flex-shrink-0 flex items-center justify-between px-6 py-3 border-t border-slate-200 bg-white text-xs text-slate-500">
          <span>
            Showing {((filters.page - 1) * filters.page_size) + 1}–{Math.min(filters.page * filters.page_size, total)} of {total.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => updateFilter({ page: filters.page - 1 })}
              disabled={filters.page <= 1}
              className="px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Prev
            </button>
            <span className="px-2">Page {filters.page}</span>
            <button
              onClick={() => updateFilter({ page: filters.page + 1 })}
              disabled={filters.page * filters.page_size >= total}
              className="px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Rule detail drawer */}
      <RuleDrawer />
    </div>
  )
}
