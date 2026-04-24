import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { listAgentRuns, getAgentStats } from '../../api/client.js'

const Ic = {
  bot:     <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="3" y="5" width="10" height="8" rx="1.5"/><circle cx="6" cy="9" r="0.8" fill="currentColor"/><circle cx="10" cy="9" r="0.8" fill="currentColor"/><path d="M8 3v2M6 13v1M10 13v1"/></svg>,
  refresh: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M13 7a5 5 0 1 0-1.5 3.5M13 3v3h-3"/></svg>,
  x:       <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 4l8 8M12 4l-8 8"/></svg>,
  warn:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M8 2l6.5 11H1.5L8 2zM8 6v3M8 11v.01"/></svg>,
}

const STATUS_PILL = {
  completed: 'active',
  started:   'paused',
  failed:    'crit',
  skipped:   'planned',
}

const AGENT_DESC = {
  extractor:       'Scans codebases and extracts automation rules into the registry',
  drift_detector:  'Compares committed rules against current code; flags drift',
  describer:       'Generates human-readable descriptions for rules',
}

function fmt(iso) {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    }).format(new Date(iso))
  } catch { return iso }
}

function relative(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

function formatMs(ms) {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

function formatTokens(n) {
  if (n == null) return '—'
  if (n < 1000) return `${n}`
  return `${(n / 1000).toFixed(1)}k`
}

function DetailDrawer({ run, onClose }) {
  if (!run) return null
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 40, display: 'flex' }}>
      <div style={{ flex: 1, background: 'rgba(18,18,18,0.2)' }} onClick={onClose} />
      <aside style={{
        width: 520, background: 'var(--vellum)',
        borderLeft: '1px solid var(--rule)', overflowY: 'auto',
        boxShadow: '-8px 0 24px rgba(0,0,0,0.06)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 16px', borderBottom: '1px solid var(--rule)' }}>
          <div>
            <div className="eyebrow">Agent run</div>
            <div style={{ fontWeight: 600, fontSize: 13.5, marginTop: 2 }}>{run.agent_name} · {run.model || '—'}</div>
          </div>
          <button className="btn sm ghost" onClick={onClose}>{Ic.x}</button>
        </div>

        <div style={{ padding: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, fontSize: 12 }}>
            <div>
              <div className="eyebrow">Status</div>
              <div style={{ marginTop: 4 }}>
                <span className={`pill ${STATUS_PILL[run.status] || 'planned'}`}><span className="dot" />{run.status}</span>
              </div>
            </div>
            <div>
              <div className="eyebrow">Step</div>
              <div style={{ marginTop: 4 }}>#{run.step_index ?? '—'}</div>
            </div>
            <div>
              <div className="eyebrow">Duration</div>
              <div style={{ marginTop: 4 }}>{formatMs(run.duration_ms)}</div>
            </div>
            <div>
              <div className="eyebrow">Tokens (in / out)</div>
              <div style={{ marginTop: 4 }}>{formatTokens(run.input_tokens)} / {formatTokens(run.output_tokens)}</div>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <div className="eyebrow">Started / finished</div>
              <div style={{ marginTop: 4 }}>{fmt(run.started_at)} → {fmt(run.finished_at)}</div>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <div className="eyebrow">Step label</div>
              <code className="mono" style={{ display: 'block', fontSize: 11, color: 'var(--ink-2)', marginTop: 4, wordBreak: 'break-all' }}>
                {run.step_label || '—'}
              </code>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <div className="eyebrow">Job ID</div>
              <code className="mono" style={{ display: 'block', fontSize: 10.5, color: 'var(--ink-3)', marginTop: 4, wordBreak: 'break-all' }}>
                {run.job_id || '—'}
              </code>
            </div>
          </div>

          {run.error && (
            <div style={{ marginTop: 16 }}>
              <div className="eyebrow" style={{ color: 'var(--risk-crit)' }}>Error</div>
              <pre className="mono" style={{ fontSize: 11, color: 'var(--risk-crit)', margin: '4px 0 0', whiteSpace: 'pre-wrap', background: 'color-mix(in srgb, var(--risk-crit) 8%, var(--vellum))', padding: 8, borderRadius: 4 }}>
{run.error}
              </pre>
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <div className="eyebrow">Input (prompt preview)</div>
            <pre className="mono" style={{ fontSize: 11, color: 'var(--ink-2)', margin: '4px 0 0', whiteSpace: 'pre-wrap', background: 'var(--paper-2)', border: '1px solid var(--rule-soft)', padding: 8, borderRadius: 4, maxHeight: 220, overflow: 'auto' }}>
{run.input_summary || '—'}
            </pre>
          </div>

          <div style={{ marginTop: 14 }}>
            <div className="eyebrow">Output (response preview)</div>
            <pre className="mono" style={{ fontSize: 11, color: 'var(--ink-2)', margin: '4px 0 0', whiteSpace: 'pre-wrap', background: 'var(--paper-2)', border: '1px solid var(--rule-soft)', padding: 8, borderRadius: 4, maxHeight: 220, overflow: 'auto' }}>
{run.output_summary || '—'}
            </pre>
          </div>
        </div>
      </aside>
    </div>
  )
}

export default function AgentLogsPage() {
  const [stats, setStats] = useState(null)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [filters, setFilters] = useState({ agent_name: '', status: '', job_id: '', limit: 100, offset: 0 })

  const activeFilters = useMemo(() => {
    const clean = { ...filters }
    Object.keys(clean).forEach((k) => { if (!clean[k]) delete clean[k] })
    return clean
  }, [filters])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [s, r] = await Promise.all([getAgentStats(), listAgentRuns(activeFilters)])
      setStats(s); setItems(r.items ?? []); setTotal(r.total ?? 0)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [activeFilters])

  useEffect(() => { load() }, [load])

  const agentOptions = Object.keys(stats?.by_agent || {})

  return (
    <div>
      <div className="page-head">
        <div className="folio">X</div>
        <h1 className="display">Agent Logs</h1>
        <p className="lede">
          Every LLM call the platform makes on your behalf. Includes the prompt preview, response preview,
          model, token counts, and latency — so you can verify what the agents are doing.
        </p>
      </div>

      <div className="kpi-row" style={{ marginBottom: 14 }}>
        <div className="kpi">
          <div className="label">Runs last 24h</div>
          <div className="num">{stats?.runs_last_24h ?? 0}</div>
        </div>
        <div className="kpi">
          <div className="label">Total runs</div>
          <div className="num">{stats?.total ?? 0}</div>
        </div>
        <div className="kpi">
          <div className="label" style={{ color: (stats?.failed_count ?? 0) > 0 ? 'var(--risk-crit)' : 'var(--ink-3)' }}>Failed</div>
          <div className="num" style={{ color: (stats?.failed_count ?? 0) > 0 ? 'var(--risk-crit)' : 'var(--ink)' }}>
            {stats?.failed_count ?? 0}
          </div>
        </div>
        <div className="kpi">
          <div className="label">Tokens (in/out)</div>
          <div className="num" style={{ fontSize: 18 }}>
            {formatTokens(stats?.total_input_tokens)} <span style={{ color: 'var(--ink-4)', fontSize: 14 }}>/</span> {formatTokens(stats?.total_output_tokens)}
          </div>
        </div>
        <div className="kpi">
          <div className="label">Avg duration</div>
          <div className="num">{formatMs(stats?.avg_duration_ms)}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className="eyebrow">Agent</span>
        <button className={`btn sm ${filters.agent_name === '' ? 'primary' : 'ghost'}`}
                onClick={() => setFilters({ ...filters, agent_name: '' })}>All</button>
        {agentOptions.map((a) => (
          <button key={a} className={`btn sm ${filters.agent_name === a ? 'primary' : 'ghost'}`}
                  onClick={() => setFilters({ ...filters, agent_name: a })}>
            {a} <span style={{ color: 'var(--ink-4)', marginLeft: 4 }}>{stats?.by_agent?.[a] ?? 0}</span>
          </button>
        ))}

        <span className="eyebrow" style={{ marginLeft: 14 }}>Status</span>
        {['', 'completed', 'failed', 'started'].map((s) => (
          <button key={s || 'all'} className={`btn sm ${filters.status === s ? 'primary' : 'ghost'}`}
                  onClick={() => setFilters({ ...filters, status: s })}>
            {s || 'All'}
          </button>
        ))}

        <button className="btn sm ghost" onClick={load} disabled={loading} style={{ marginLeft: 'auto' }}>
          {Ic.refresh}<span>Refresh</span>
        </button>
      </div>

      {error && <div className="pill crit" style={{ marginBottom: 8 }}>{Ic.warn}<span>{error}</span></div>}

      {filters.agent_name && AGENT_DESC[filters.agent_name] && (
        <p style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 10, fontStyle: 'italic' }}>
          {AGENT_DESC[filters.agent_name]}
        </p>
      )}

      <div className="l-card" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="l-table">
          <thead>
            <tr>
              <th style={{ width: 140 }}>When</th>
              <th>Agent</th>
              <th>Step</th>
              <th>Model</th>
              <th>Tokens</th>
              <th>Duration</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={7} style={{ padding: 40, textAlign: 'center', color: 'var(--ink-4)' }}>
                  <div style={{ marginBottom: 6 }}>{Ic.bot}</div>
                  <div style={{ fontSize: 13 }}>No agent runs match this filter.</div>
                </td>
              </tr>
            )}
            {items.map((r) => (
              <tr key={r.id} onClick={() => setSelected(r)}>
                <td style={{ fontSize: 11, color: 'var(--ink-4)', fontFamily: 'var(--ff-mono)' }}>
                  <div>{relative(r.started_at)}</div>
                  <div style={{ fontSize: 10 }}>{fmt(r.started_at)}</div>
                </td>
                <td style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                  <div style={{ fontWeight: 500 }}>{r.agent_name}</div>
                  <div style={{ fontSize: 10, color: 'var(--ink-4)' }}>{r.agent_version}</div>
                </td>
                <td>
                  <div style={{ fontSize: 11.5, color: 'var(--ink-2)', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {r.step_label || '—'}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--ink-4)' }}>#{r.step_index ?? '—'}</div>
                </td>
                <td style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--ff-mono)' }}>{r.model || '—'}</td>
                <td style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                  {formatTokens(r.input_tokens)}<span style={{ color: 'var(--ink-5)' }}> / </span>{formatTokens(r.output_tokens)}
                </td>
                <td style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{formatMs(r.duration_ms)}</td>
                <td>
                  <span className={`pill ${STATUS_PILL[r.status] || 'planned'}`} style={{ fontSize: 10.5 }}>
                    <span className="dot" />{r.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {total > items.length && (
          <div style={{ padding: 10, borderTop: '1px solid var(--rule-hair)', fontSize: 11.5, color: 'var(--ink-4)', textAlign: 'center' }}>
            Showing {items.length} of {total}
          </div>
        )}
      </div>

      <DetailDrawer run={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
