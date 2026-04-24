import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { getFileAccessLogs, getFileAccessStats, flagFileAccess } from '../../api/client.js'

const Ic = {
  search:  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5l3 3"/></svg>,
  refresh: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M13 7a5 5 0 1 0-1.5 3.5M13 3v3h-3"/></svg>,
  x:       <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 4l8 8M12 4l-8 8"/></svg>,
  file:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/></svg>,
  warn:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M8 2l6.5 11H1.5L8 2zM8 6v3M8 11v.01"/></svg>,
  check:   <svg width="13" height="13" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M2 6.5l2.5 2.5L10 3.5"/></svg>,
  shield:  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M8 2l5 2v4c0 3-2.2 5-5 6-2.8-1-5-3-5-6V4l5-2z"/></svg>,
}

const SOURCE_LABELS = {
  local: 'Local',
  git: 'Git',
  dms: 'DMS',
  cloud: 'Cloud',
  other: 'Other',
}

const ACTION_LABELS = {
  read: 'Read',
  listed: 'Listed',
  skipped_size: 'Skipped (too large)',
  skipped_ext: 'Skipped (unsupported)',
  skipped_error: 'Skipped (error)',
}

const SENSITIVITY_PILL = {
  ok:      'active',
  flagged: 'crit',
  unknown: 'planned',
}

// ------------------------------------------------------------- PII parsing
// Prefer the first-class `pii_tags` column. Older rows (seeded before the
// column existed) carry findings in the reason string; we parse those as a
// fallback so historical data still renders.
const PII_RE = /PII detected: ([^.]+?)(?:\.|$)/i
function getPII(entry) {
  if (entry.pii_tags && entry.pii_tags.length > 0) {
    return entry.pii_tags.map((t) => ({ label: t.label, count: t.count, tag: t.tag }))
  }
  const reason = entry.reason
  if (!reason) return []
  const m = reason.match(PII_RE)
  if (!m) return []
  return m[1].split(',').map((s) => {
    const t = s.trim()
    const [, label, countStr] = t.match(/^(.+?)(?:\s*×\s*(\d+))?$/) || []
    return { label: label || t, count: countStr ? +countStr : 1 }
  })
}

function formatBytes(n) {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function formatRelative(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

// ----------------------------------------------------------- detail drawer
function DetailDrawer({ entry, onClose, onFlag }) {
  const [pending, setPending] = useState(false)
  const [note, setNote] = useState('')
  if (!entry) return null

  const pii = getPII(entry)

  const handleFlag = async (sensitivity) => {
    setPending(true)
    try {
      const updated = await flagFileAccess(entry.id, { sensitivity, reason: note || undefined })
      onFlag(updated)
    } finally {
      setPending(false); setNote('')
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 40, display: 'flex' }}>
      <div style={{ flex: 1, background: 'rgba(18,18,18,0.2)' }} onClick={onClose} />
      <aside style={{
        width: 440,
        background: 'var(--vellum)',
        borderLeft: '1px solid var(--rule)',
        overflowY: 'auto',
        boxShadow: '-8px 0 24px rgba(0,0,0,0.06)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 16px', borderBottom: '1px solid var(--rule)' }}>
          <div className="eyebrow">File access detail</div>
          <button className="btn sm ghost" onClick={onClose}>{Ic.x}</button>
        </div>

        <div style={{ padding: 16 }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>Path</div>
          <code className="mono" style={{
            display: 'block', fontSize: 11.5,
            background: 'var(--paper-2)', border: '1px solid var(--rule-soft)',
            borderRadius: 4, padding: '6px 8px', wordBreak: 'break-all',
            color: 'var(--ink-2)',
          }}>
            {entry.path}
          </code>

          {pii.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div className="eyebrow" style={{ color: 'var(--risk-crit)', marginBottom: 6 }}>PII detected</div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {pii.map((p, i) => (
                  <span key={i} className="pill crit" style={{ fontSize: 10.5 }}>
                    {p.label}{p.count > 1 && <span style={{ marginLeft: 4, opacity: 0.8 }}>×{p.count}</span>}
                  </span>
                ))}
              </div>
              <p style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 6, fontStyle: 'italic' }}>
                Detected by the regex content classifier. Sensitivity was auto-escalated to flagged.
              </p>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 14, fontSize: 12 }}>
            <div>
              <div className="eyebrow">Source</div>
              <div style={{ marginTop: 2 }}>{SOURCE_LABELS[entry.source_type] ?? entry.source_type}</div>
              {entry.source_name && <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>{entry.source_name}</div>}
            </div>
            <div>
              <div className="eyebrow">Action</div>
              <div style={{ marginTop: 2 }}>{ACTION_LABELS[entry.action] ?? entry.action}</div>
            </div>
            <div>
              <div className="eyebrow">Size</div>
              <div style={{ marginTop: 2 }}>{formatBytes(entry.size_bytes)}</div>
            </div>
            <div>
              <div className="eyebrow">Language</div>
              <div style={{ marginTop: 2 }}>{entry.language ?? '—'}</div>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <div className="eyebrow">Accessed</div>
              <div style={{ marginTop: 2 }}>{new Date(entry.accessed_at).toLocaleString()}</div>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <div className="eyebrow">Extraction job</div>
              <code className="mono" style={{
                display: 'block', fontSize: 10.5, marginTop: 2,
                background: 'var(--paper-2)', border: '1px solid var(--rule-soft)',
                borderRadius: 3, padding: '4px 6px', wordBreak: 'break-all',
              }}>{entry.extraction_job_id ?? '—'}</code>
            </div>
            {entry.content_hash && (
              <div style={{ gridColumn: 'span 2' }}>
                <div className="eyebrow">SHA-256</div>
                <code className="mono" style={{ fontSize: 10, color: 'var(--ink-3)', display: 'block', marginTop: 2, wordBreak: 'break-all' }}>
                  {entry.content_hash}
                </code>
              </div>
            )}
            {entry.reason && (
              <div style={{ gridColumn: 'span 2' }}>
                <div className="eyebrow">Reason</div>
                <div style={{ marginTop: 2, fontSize: 11.5, color: 'var(--ink-2)' }}>{entry.reason}</div>
              </div>
            )}
          </div>

          <div style={{ paddingTop: 14, marginTop: 14, borderTop: '1px solid var(--rule-hair)' }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Sensitivity</div>
            <div style={{ marginBottom: 10 }}>
              <span className={`pill ${SENSITIVITY_PILL[entry.sensitivity] ?? 'planned'}`}>
                <span className="dot" />{entry.sensitivity}
              </span>
            </div>
            <div className="input" style={{ marginBottom: 8 }}>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note for the audit trail…" />
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button disabled={pending} onClick={() => handleFlag('flagged')}
                      className="btn sm" style={{ color: 'var(--risk-crit)', borderColor: 'var(--risk-crit)', flex: 1 }}>
                {Ic.warn}<span>Flag as accidental</span>
              </button>
              <button disabled={pending} onClick={() => handleFlag('ok')}
                      className="btn sm" style={{ color: 'var(--ok)', borderColor: 'var(--ok)', flex: 1 }}>
                {Ic.check}<span>Mark OK</span>
              </button>
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}

// ----------------------------------------------------------- main page
export default function DataAccessPage() {
  const [stats, setStats] = useState(null)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)

  const [filters, setFilters] = useState({
    search: '', source_type: '', action: '', sensitivity: '',
    extraction_job_id: '', limit: 100, offset: 0,
  })

  const activeFilters = useMemo(() => {
    const clean = { ...filters }
    Object.keys(clean).forEach((k) => {
      if (clean[k] === '' || clean[k] == null) delete clean[k]
    })
    return clean
  }, [filters])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [statsData, listData] = await Promise.all([
        getFileAccessStats(),
        getFileAccessLogs(activeFilters),
      ])
      setStats(statsData)
      setItems(listData.items ?? [])
      setTotal(listData.total ?? 0)
    } catch (e) {
      setError(e.message ?? 'Failed to load file-access data')
    } finally { setLoading(false) }
  }, [activeFilters])

  useEffect(() => { load() }, [load])

  const handleFlagged = (updated) => {
    setItems((prev) => prev.map((it) => (it.id === updated.id ? updated : it)))
    setSelected(updated)
    load()
  }

  const flaggedCount = stats?.flagged_count ?? 0
  const totalFiles = stats?.total_files ?? 0
  const readCount = stats?.by_action?.read ?? 0
  const skippedCount =
    (stats?.by_action?.skipped_size ?? 0) +
    (stats?.by_action?.skipped_ext ?? 0) +
    (stats?.by_action?.skipped_error ?? 0)

  // Count PII-detected items visible in current table
  const piiCount = items.filter((e) => getPII(e).length > 0).length

  return (
    <div>
      <div className="page-head">
        <div className="folio">VII</div>
        <h1 className="display">Data Access</h1>
        <p className="lede">
          Every file the extraction agent has touched — what it read, skipped, or flagged.
          Sensitivity is escalated automatically when filename or content matches a sensitive pattern.
        </p>
      </div>

      {/* KPI row */}
      <div className="kpi-row" style={{ marginBottom: 16 }}>
        <div className="kpi"><div className="label">Files touched</div><div className="num">{totalFiles}</div></div>
        <div className="kpi"><div className="label">Reads</div><div className="num">{readCount}</div></div>
        <div className="kpi"><div className="label">Skipped</div><div className="num">{skippedCount}</div></div>
        <div className="kpi">
          <div className="label" style={{ color: flaggedCount > 0 ? 'var(--risk-crit)' : 'var(--ink-3)' }}>Flagged</div>
          <div className="num" style={{ color: flaggedCount > 0 ? 'var(--risk-crit)' : 'var(--ink)' }}>{flaggedCount}</div>
        </div>
      </div>

      {/* filter row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <div className="input" style={{ flex: '1 1 240px', minWidth: 200 }}>
          <span className="pre">{Ic.search}</span>
          <input placeholder="Search paths…"
                 value={filters.search}
                 onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value, offset: 0 }))} />
        </div>

        <select value={filters.source_type}
                onChange={(e) => setFilters((f) => ({ ...f, source_type: e.target.value, offset: 0 }))}
                style={{ fontSize: 12, padding: '5px 8px', border: '1px solid var(--rule)', background: 'var(--vellum)', borderRadius: 4 }}>
          <option value="">All sources</option>
          {Object.entries(SOURCE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>

        <select value={filters.action}
                onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value, offset: 0 }))}
                style={{ fontSize: 12, padding: '5px 8px', border: '1px solid var(--rule)', background: 'var(--vellum)', borderRadius: 4 }}>
          <option value="">All actions</option>
          {Object.entries(ACTION_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>

        <select value={filters.sensitivity}
                onChange={(e) => setFilters((f) => ({ ...f, sensitivity: e.target.value, offset: 0 }))}
                style={{ fontSize: 12, padding: '5px 8px', border: '1px solid var(--rule)', background: 'var(--vellum)', borderRadius: 4 }}>
          <option value="">Any sensitivity</option>
          <option value="flagged">Flagged</option>
          <option value="ok">OK</option>
          <option value="unknown">Unknown</option>
        </select>

        {Object.keys(activeFilters).some((k) => !['limit', 'offset'].includes(k)) && (
          <button className="btn sm ghost"
                  onClick={() => setFilters({ search: '', source_type: '', action: '', sensitivity: '', extraction_job_id: '', limit: 100, offset: 0 })}>
            {Ic.x}<span>Clear</span>
          </button>
        )}

        <button className="btn sm ghost" onClick={load} disabled={loading} style={{ marginLeft: 'auto' }}>
          {Ic.refresh}<span>Refresh</span>
        </button>
      </div>

      {piiCount > 0 && (
        <div className="pill crit" style={{ marginBottom: 10 }}>
          {Ic.shield}
          <span><strong>{piiCount}</strong> file{piiCount !== 1 && 's'} in this view contain detected PII</span>
        </div>
      )}

      {error && <div className="pill crit" style={{ marginBottom: 10 }}>{Ic.warn}<span>{error}</span></div>}

      {/* table */}
      <div className="l-card" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="l-table">
          <thead>
            <tr>
              <th style={{ width: '38%' }}>Path</th>
              <th>Source</th>
              <th>Action</th>
              <th>Size</th>
              <th>PII</th>
              <th>Sensitivity</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={7} style={{ padding: 40, textAlign: 'center', color: 'var(--ink-4)' }}>
                  <div style={{ marginBottom: 6 }}>{Ic.file}</div>
                  <div style={{ fontSize: 13 }}>No file-access records match this filter.</div>
                  <div style={{ fontSize: 11, marginTop: 4 }}>Run an extraction to populate this view.</div>
                </td>
              </tr>
            )}
            {items.map((entry) => {
              const pii = getPII(entry)
              return (
                <tr key={entry.id} onClick={() => setSelected(entry)}>
                  <td>
                    <code className="mono" style={{ fontSize: 11.5, color: 'var(--ink-2)', wordBreak: 'break-all' }}>
                      {entry.path}
                    </code>
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--ink-3)' }}>{SOURCE_LABELS[entry.source_type] ?? entry.source_type}</td>
                  <td style={{ fontSize: 12, color: 'var(--ink-3)' }}>{ACTION_LABELS[entry.action] ?? entry.action}</td>
                  <td style={{ fontSize: 12, color: 'var(--ink-3)' }}>{formatBytes(entry.size_bytes)}</td>
                  <td>
                    {pii.length > 0 ? (
                      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap', maxWidth: 180 }}>
                        {pii.slice(0, 2).map((p, i) => (
                          <span key={i} className="pill crit" style={{ fontSize: 10, padding: '1px 5px' }}>
                            {p.label}{p.count > 1 && <span style={{ marginLeft: 3 }}>×{p.count}</span>}
                          </span>
                        ))}
                        {pii.length > 2 && (
                          <span className="pill" style={{ fontSize: 10, padding: '1px 5px' }}>
                            +{pii.length - 2}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span style={{ color: 'var(--ink-5)', fontSize: 11 }}>—</span>
                    )}
                  </td>
                  <td>
                    <span className={`pill ${SENSITIVITY_PILL[entry.sensitivity] ?? 'planned'}`} style={{ fontSize: 10.5 }}>
                      <span className="dot" />{entry.sensitivity}
                    </span>
                  </td>
                  <td style={{ fontSize: 11, color: 'var(--ink-4)' }}>{formatRelative(entry.accessed_at)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {total > items.length && (
          <div style={{ padding: 10, borderTop: '1px solid var(--rule-hair)', fontSize: 11.5, color: 'var(--ink-4)', textAlign: 'center' }}>
            Showing {items.length} of {total}
          </div>
        )}
      </div>

      <DetailDrawer entry={selected} onClose={() => setSelected(null)} onFlag={handleFlagged} />
    </div>
  )
}
