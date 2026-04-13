import React, { useState, useEffect, useCallback } from 'react'
import {
  Download, Search, RefreshCw, Filter,
  Edit2, CheckCircle2, Plus, Trash2, Clock,
  ChevronLeft, ChevronRight,
} from 'lucide-react'
import clsx from 'clsx'
import { getAuditLog, exportAudit } from '../../api/client.js'

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_ENTRIES = Array.from({ length: 40 }, (_, i) => {
  const actions   = ['edit', 'verify', 'add', 'delete', 'import']
  const operators = ['alice@co.com', 'bob@co.com', 'carol@co.com', 'system', 'dave@co.com']
  const rule_ids  = ['FIN-001', 'FIN-002', 'OPS-007', 'IT-031', 'HR-012', 'SALES-003', 'MKT-002']
  const descriptions = [
    'Updated threshold from 1000 to 5000',
    'Marked as verified by operator',
    'Ingested via extraction job #44',
    'Changed retry_limit from 3 to 5',
    'Disabled budget_cap flag',
    'Updated notify_list to include security@co.com',
    'Changed approval_chain to manager → director',
    'Updated cron schedule to 0 9 * * 1-5',
  ]

  return {
    id:          i + 1,
    timestamp:   new Date(Date.now() - i * 2_400_000).toISOString(),
    action:      actions[i % actions.length],
    operator:    operators[i % operators.length],
    rule_id:     rule_ids[i % rule_ids.length],
    description: descriptions[i % descriptions.length],
    field:       i % 2 === 0 ? 'threshold' : undefined,
    old_value:   i % 2 === 0 ? '1000' : undefined,
    new_value:   i % 2 === 0 ? '5000' : undefined,
  }
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelative(isoString) {
  const now  = Date.now()
  const then = new Date(isoString).getTime()
  const diffMs = now - then
  const diffMins  = Math.floor(diffMs / 60_000)
  const diffHours = Math.floor(diffMs / 3_600_000)
  const diffDays  = Math.floor(diffMs / 86_400_000)

  if (diffMins < 1)   return 'just now'
  if (diffMins < 60)  return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7)   return `${diffDays}d ago`

  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(isoString))
}

const ACTION_CONFIG = {
  edit:   { Icon: Edit2,        color: 'bg-slate-100 text-slate-600 border-slate-200', label: 'Edit' },
  verify: { Icon: CheckCircle2, color: 'bg-slate-100 text-slate-600 border-slate-200', label: 'Verify' },
  add:    { Icon: Plus,         color: 'bg-slate-100 text-slate-600 border-slate-200', label: 'Add' },
  delete: { Icon: Trash2,       color: 'bg-red-50 text-red-600 border-red-200',        label: 'Delete' },
  import: { Icon: Download,     color: 'bg-slate-100 text-slate-600 border-slate-200', label: 'Import' },
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

function AuditFilterBar({ filters, onChange }) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="relative flex-1 min-w-48">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type="text"
          placeholder="Search rule ID or operator…"
          value={filters.search ?? ''}
          onChange={e => onChange({ search: e.target.value })}
          className="
            w-full pl-8 pr-3 py-1.5 text-sm rounded-lg border border-slate-200 bg-white
            focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-slate-400
          "
        />
      </div>

      <select
        value={filters.action ?? ''}
        onChange={e => onChange({ action: e.target.value })}
        className="select-field text-sm py-1.5 px-3 rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-slate-400 text-slate-700"
      >
        <option value="">All actions</option>
        {Object.entries(ACTION_CONFIG).map(([k, v]) => (
          <option key={k} value={k}>{v.label}</option>
        ))}
      </select>

      <select
        value={filters.operator ?? ''}
        onChange={e => onChange({ operator: e.target.value })}
        className="select-field text-sm py-1.5 px-3 rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-slate-400 text-slate-700"
      >
        <option value="">All operators</option>
        {['alice@co.com', 'bob@co.com', 'carol@co.com', 'dave@co.com', 'system'].map(op => (
          <option key={op} value={op}>{op}</option>
        ))}
      </select>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Audit entry row
// ---------------------------------------------------------------------------

function AuditRow({ entry }) {
  const cfg = ACTION_CONFIG[entry.action] ?? ACTION_CONFIG.edit
  const { Icon } = cfg

  return (
    <tr className="border-b border-slate-100 bg-white hover:bg-slate-50 transition-colors">
      {/* Timestamp */}
      <td className="px-4 py-3 w-32">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-medium text-slate-700 whitespace-nowrap tabular-nums">
            {formatRelative(entry.timestamp)}
          </span>
          <span className="text-[10px] text-slate-400 whitespace-nowrap">
            {new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(new Date(entry.timestamp))}
          </span>
        </div>
      </td>

      {/* Action */}
      <td className="px-4 py-3 w-28">
        <span className={clsx(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold whitespace-nowrap',
          cfg.color
        )}>
          <Icon size={11} />
          {cfg.label}
        </span>
      </td>

      {/* Rule ID */}
      <td className="px-4 py-3 w-28">
        <code className="font-mono text-xs text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded">
          {entry.rule_id}
        </code>
      </td>

      {/* Description + diff */}
      <td className="px-4 py-3">
        <p className="text-sm text-slate-700">{entry.description}</p>
        {entry.field && (
          <div className="flex items-center gap-1.5 mt-1.5 font-mono text-xs">
            <span className="text-slate-400">{entry.field}:</span>
            <span className="text-slate-400 line-through">
              {entry.old_value}
            </span>
            <span className="text-slate-400">→</span>
            <span className="text-slate-800 font-medium">
              {entry.new_value}
            </span>
          </div>
        )}
      </td>

      {/* Operator */}
      <td className="px-4 py-3 w-36">
        <span className="text-xs text-slate-500 truncate block">
          {entry.operator === 'system' ? (
            <span className="italic text-slate-400">system</span>
          ) : entry.operator}
        </span>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// AuditPage
// ---------------------------------------------------------------------------

export default function AuditPage() {
  const [entries, setEntries]     = useState(MOCK_ENTRIES)
  const [loading, setLoading]     = useState(false)
  const [exporting, setExporting] = useState(false)
  const [filters, setFilters]     = useState({ search: '', action: '', operator: '' })
  const [page, setPage]           = useState(1)
  const PAGE_SIZE = 20

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getAuditLog({ ...filters, page, page_size: PAGE_SIZE })
      setEntries(data.items ?? data)
    } catch {
      setEntries(MOCK_ENTRIES)
    } finally {
      setLoading(false)
    }
  }, [filters, page])

  useEffect(() => { load() }, [load])

  const handleFilterChange = (patch) => {
    setFilters(prev => ({ ...prev, ...patch }))
    setPage(1)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await exportAudit(filters)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `runbook-audit-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Export failed — try again.')
    } finally {
      setExporting(false)
    }
  }

  // Client-side filter on mock data
  const filtered = entries.filter(e => {
    const q = (filters.search ?? '').toLowerCase()
    const matchSearch = !q ||
      e.rule_id.toLowerCase().includes(q) ||
      e.operator.toLowerCase().includes(q) ||
      e.description.toLowerCase().includes(q)
    const matchAction   = !filters.action   || e.action === filters.action
    const matchOperator = !filters.operator || e.operator === filters.operator
    return matchSearch && matchAction && matchOperator
  })

  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-slate-200 bg-white space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Audit Log</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {filtered.length.toLocaleString()} entries
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={load}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button
              onClick={handleExport}
              disabled={exporting}
              className="
                flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg
                bg-white border border-slate-200 text-slate-700 hover:bg-slate-50
                disabled:opacity-50 transition-colors
              "
            >
              <Download size={14} />
              {exporting ? 'Exporting…' : 'Export CSV'}
            </button>
          </div>
        </div>
        <AuditFilterBar filters={filters} onChange={handleFilterChange} />
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto scrollbar-thin">
        <table className="w-full border-collapse min-w-[800px]">
          <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 z-10">
            <tr>
              {[
                { label: 'When',     w: 'w-32' },
                { label: 'Action',   w: 'w-28' },
                { label: 'Rule ID',  w: 'w-28' },
                { label: 'Change',   w: 'flex-1' },
                { label: 'Operator', w: 'w-36' },
              ].map(col => (
                <th key={col.label} scope="col" className={clsx('px-4 py-2.5 text-left', col.w)}>
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    {col.label}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="text-center py-16 text-slate-400 text-sm bg-white">
                  <RefreshCw size={20} className="animate-spin mx-auto mb-2" />
                  Loading audit log…
                </td>
              </tr>
            ) : paginated.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-16 text-slate-400 text-sm bg-white">
                  No entries match your filters.
                </td>
              </tr>
            ) : (
              paginated.map((entry) => (
                <AuditRow key={entry.id} entry={entry} />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-3 border-t border-slate-200 bg-white text-xs text-slate-500">
        <span>
          Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="p-1.5 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            aria-label="Previous page"
          >
            <ChevronLeft size={12} />
          </button>
          <span className="px-2">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="p-1.5 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            aria-label="Next page"
          >
            <ChevronRight size={12} />
          </button>
        </div>
      </div>
    </div>
  )
}
