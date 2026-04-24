import React, { useState, useEffect, useCallback, useRef } from 'react'
import { getAuditLog, exportAudit } from '../../api/client.js'

const MOCK_ENTRIES = Array.from({ length: 40 }, (_, i) => {
  const actions   = ['edit', 'verify', 'add', 'delete', 'import']
  const operators = ['alice@co.com', 'bob@co.com', 'carol@co.com', 'system', 'dave@co.com']
  const rule_ids  = ['FIN-001', 'FIN-002', 'OPS-007', 'IT-031', 'HR-012', 'SLS-003', 'MKT-002']
  const descriptions = [
    'updated threshold from 1000 to 5000',
    'marked as verified',
    'ingested via extraction job #44',
    'changed retry_limit from 3 to 5',
    'disabled budget_cap flag',
    'updated notify_list to include security@co.com',
    'changed approval_chain to manager → director',
    'updated cron schedule to 0 9 * * 1-5',
  ]
  return {
    id: i + 1,
    timestamp: new Date(Date.now() - i * 2_400_000).toISOString(),
    action: actions[i % actions.length],
    operator: operators[i % operators.length],
    rule_id: rule_ids[i % rule_ids.length],
    description: descriptions[i % descriptions.length],
    field: i % 3 === 0 ? 'threshold' : undefined,
    old_value: i % 3 === 0 ? '1000' : undefined,
    new_value: i % 3 === 0 ? '5000' : undefined,
  }
})

const Ic = {
  search:  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5l3 3"/></svg>,
  down:    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 4.5l3 3 3-3"/></svg>,
  refresh: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M13 7a5 5 0 1 0-1.5 3.5M13 3v3h-3"/></svg>,
}

const ACTIONS = ['All', 'edit', 'verify', 'add', 'delete', 'import']

function formatWhen(iso) {
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(new Date(iso))
  } catch { return iso }
}

function Pill({ kind, children }) {
  return <span className={`pill${kind ? ` ${kind}` : ''}`}>{kind && <span className="dot" />}{children}</span>
}

function Dd({ label, value, onChange, options }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDoc = e => { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])
  const displayValue = value === '' ? 'All' : value.charAt(0).toUpperCase() + value.slice(1)
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <div className="select" onClick={() => setOpen(o => !o)}>
        <span className="lbl">{label}:</span>
        <span>{displayValue}</span>
        <span className="caret">{Ic.down}</span>
      </div>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', right: 0,
          background: 'var(--vellum)', border: '1px solid var(--rule)',
          minWidth: 160, zIndex: 20, padding: 4, borderRadius: 'var(--radius)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
        }}>
          {options.map(o => {
            const optionValue = o === 'All' ? '' : o
            const displayLabel = o === 'All' ? 'All' : o.charAt(0).toUpperCase() + o.slice(1)
            return (
              <div key={o} onClick={() => { onChange(optionValue); setOpen(false) }}
                style={{
                  padding: '6px 10px', fontSize: 12.5, cursor: 'pointer',
                  borderRadius: 4,
                  background: optionValue === value ? 'var(--paper-2)' : 'transparent',
                  color: 'var(--ink-2)',
                }}>
                {displayLabel}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

const ACTION_KIND = { verify: 'active', add: 'planned', delete: 'crit', edit: '', import: 'planned' }

export default function AuditPage() {
  const [entries, setEntries] = useState(MOCK_ENTRIES)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [filters, setFilters] = useState({ search: '', action: '' })
  const [page, setPage] = useState(1)
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
    } catch { alert('Export failed — try again.') }
    finally { setExporting(false) }
  }

  const filtered = entries.filter(e => {
    const q = (filters.search ?? '').toLowerCase()
    const matchSearch = !q ||
      e.rule_id?.toLowerCase().includes(q) ||
      e.operator?.toLowerCase().includes(q) ||
      e.description?.toLowerCase().includes(q)
    const matchAction = !filters.action || e.action === filters.action
    return matchSearch && matchAction
  })
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))

  return (
    <>
      <header className="page-head">
        <div>
          <div className="folio">§ VII · Audit Log</div>
          <h1>Audit <em>log</em></h1>
          <div className="lede">
            Every edit, enrollment, and verification — in order, retained permanently.
          </div>
        </div>
        <div className="head-actions">
          <button className="btn sm" onClick={load} disabled={loading}>
            {Ic.refresh} Refresh
          </button>
          <button className="btn sm" onClick={handleExport} disabled={exporting}>
            {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
        </div>
      </header>

      <div className="l-row mb16" style={{ gap: 10, flexWrap: 'wrap' }}>
        <div className="input" style={{ flex: 1, minWidth: 280, maxWidth: 440 }}>
          <span className="pre">{Ic.search}</span>
          <input
            placeholder="Search by rule id or operator…"
            value={filters.search}
            onChange={e => { setFilters(f => ({ ...f, search: e.target.value })); setPage(1) }}
          />
        </div>
        <div className="right l-row gap8">
          <Dd
            label="Action"
            value={filters.action}
            onChange={v => { setFilters(f => ({ ...f, action: v })); setPage(1) }}
            options={ACTIONS}
          />
        </div>
      </div>

      <div className="table-wrap">
        <table className="l-table">
          <thead>
            <tr>
              <th style={{ width: 150 }}>When</th>
              <th style={{ width: 100 }}>Action</th>
              <th style={{ width: 130 }}>Rule</th>
              <th>Change</th>
              <th style={{ width: 180 }}>Operator</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--ink-4)' }}>Loading audit log…</td></tr>
            ) : paginated.length === 0 ? (
              <tr><td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--ink-4)' }}>No entries match your filters.</td></tr>
            ) : paginated.map(e => (
              <tr key={e.id} className={e.action === 'verify' ? 'focus-row' : ''}>
                <td className="mono dim" style={{ fontSize: 12 }}>{formatWhen(e.timestamp)}</td>
                <td>
                  <Pill kind={ACTION_KIND[e.action]}>
                    {e.action ? e.action.charAt(0).toUpperCase() + e.action.slice(1) : '—'}
                  </Pill>
                </td>
                <td className="id-cell">{e.rule_id}</td>
                <td>
                  <span className="dim">{e.description}</span>
                  {e.field && (
                    <div className="mono" style={{ fontSize: 11.5, marginTop: 4, color: 'var(--ink-4)' }}>
                      {e.field}: <span style={{ textDecoration: 'line-through' }}>{e.old_value}</span>
                      {' → '}
                      <span style={{ color: 'var(--ink), fontWeight: 500' }}>{e.new_value}</span>
                    </div>
                  )}
                </td>
                <td className="mono dim" style={{ fontSize: 12 }}>
                  {e.operator === 'system'
                    ? <em style={{ fontStyle: 'italic', color: 'var(--ink-4)' }}>system</em>
                    : e.operator}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filtered.length > PAGE_SIZE && (
        <div className="l-row mt16" style={{ justifyContent: 'space-between' }}>
          <div className="dim" style={{ fontSize: 12 }}>
            Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
          </div>
          <div className="l-row gap8">
            <button className="btn sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>‹</button>
            <span className="mono dim" style={{ fontSize: 12 }}>{page} / {totalPages}</span>
            <button className="btn sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>›</button>
          </div>
        </div>
      )}
    </>
  )
}
