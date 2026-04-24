import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getDashboardStats, getAuditLog,
  listPendingChanges, listAttestations, listFreezeWindows,
  getFileAccessStats,
  listAgentRuns, getAgentStats,
} from '../../api/client.js'

// ---------- mock fallback ----------
const MOCK_STATS = {
  total_rules: 142,
  active_rules: 118,
  unverified_rules: 23,
  recent_changes: 7,
  departments: [
    { name: 'Finance',     count: 31, pct: 22 },
    { name: 'Operations',  count: 28, pct: 20 },
    { name: 'Engineering', count: 24, pct: 17 },
    { name: 'People',      count: 19, pct: 13 },
    { name: 'Sales',       count: 16, pct: 11 },
    { name: 'Marketing',   count: 12, pct:  8 },
    { name: 'Legal',       count:  8, pct:  6 },
    { name: 'Other',       count:  4, pct:  3 },
  ],
  risk_distribution: { low: 68, medium: 47, high: 21, critical: 6 },
  extraction_health: { last_scan: '2026-04-23T03:00:00Z', drift_status: 'clean', files_scanned: 312 },
}

const MOCK_AUDIT = [
  { id: 1, timestamp: '2026-04-23T14:22:00Z', action: 'edit',   operator: 'alice@co.com',  rule_id: 'FIN-004', description: 'updated threshold to 5,000' },
  { id: 2, timestamp: '2026-04-23T13:08:00Z', action: 'verify', operator: 'bob@co.com',    rule_id: 'HR-012',  description: 'marked as verified' },
  { id: 3, timestamp: '2026-04-23T11:54:00Z', action: 'edit',   operator: 'carol@co.com',  rule_id: 'OPS-007', description: 'changed retry_limit from 3 to 5' },
  { id: 4, timestamp: '2026-04-23T09:30:00Z', action: 'add',    operator: 'system',        rule_id: 'IT-031',  description: 'ingested via extraction job #44' },
  { id: 5, timestamp: '2026-04-22T17:12:00Z', action: 'edit',   operator: 'alice@co.com',  rule_id: 'FIN-011', description: 'updated notify_list' },
  { id: 6, timestamp: '2026-04-22T16:44:00Z', action: 'verify', operator: 'dave@co.com',   rule_id: 'SLS-003', description: 'marked as verified' },
  { id: 7, timestamp: '2026-04-22T14:02:00Z', action: 'edit',   operator: 'carol@co.com',  rule_id: 'MKT-002', description: 'disabled budget_cap' },
  { id: 8, timestamp: '2026-04-22T10:18:00Z', action: 'add',    operator: 'system',        rule_id: 'IT-030',  description: 'ingested via extraction job #43' },
]

const Ic = {
  list:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M4 4h9M4 8h9M4 12h9"/></svg>,
  check:   <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M2 6.5l2.5 2.5L10 3.5"/></svg>,
  bell:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M4 11v-3a4 4 0 0 1 8 0v3l1 1H3l1 -1z"/></svg>,
  log:     <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="3" y="2.5" width="10" height="11" rx="1"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3"/></svg>,
  refresh: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M13 7a5 5 0 1 0-1.5 3.5M13 3v3h-3"/></svg>,
  plus:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 3v10M3 8h10"/></svg>,
  arrow:   <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 6h8M7 3l3 3-3 3"/></svg>,
  play:    <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M3 2l7 4-7 4z"/></svg>,
  flow:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="3" cy="8" r="1.6"/><circle cx="13" cy="4" r="1.6"/><circle cx="13" cy="12" r="1.6"/><path d="M4.5 7.2l7 -2.6M4.5 8.8l7 2.6"/></svg>,
  scan:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M3 3h2M3 3v2M13 3h-2M13 3v2M3 13h2M3 13v-2M13 13h-2M13 13v-2M5 8h6"/></svg>,
}

const RISK_META = {
  critical: { tier: 'Critical', key: 'crit', caption: 'require sign-off',  var: 'var(--risk-crit)' },
  high:     { tier: 'High',     key: 'high', caption: 'monitored daily',    var: 'var(--risk-high)' },
  medium:   { tier: 'Medium',   key: 'med',  caption: 'weekly review',      var: 'var(--risk-med)'  },
  low:      { tier: 'Low',      key: 'low',  caption: 'routine',            var: 'var(--risk-low)'  },
}
const RISK_ORDER = ['critical', 'high', 'medium', 'low']

function formatWhen(iso) {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(new Date(iso)).replace(',', ' ·')
  } catch {
    return iso
  }
}

function Pill({ kind, children }) {
  return (
    <span className={`pill${kind ? ` ${kind}` : ''}`}>
      {kind && <span className="dot" />}
      {children}
    </span>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [audit, setAudit] = useState([])
  const [loading, setLoading] = useState(true)
  const [govStats, setGovStats] = useState({ pending: 0, overdue: 0, flagged: 0, freezes: 0 })
  const [agentStats, setAgentStats] = useState(null)
  const [agentRuns, setAgentRuns] = useState([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, a] = await Promise.all([
        getDashboardStats(),
        getAuditLog({ page_size: 10 }),
      ])
      setStats(s)
      setAudit(a.items ?? a)
    } catch {
      setStats(MOCK_STATS)
      setAudit(MOCK_AUDIT)
    } finally {
      setLoading(false)
    }

    // Governance tiles + agent activity — fire-and-forget, never block the page
    try {
      const [pc, att, fw, fa, as, ar] = await Promise.all([
        listPendingChanges({ status: 'pending', limit: 1 }).catch(() => ({ total: 0 })),
        listAttestations({ status: 'overdue', limit: 1 }).catch(() => ({ total: 0 })),
        listFreezeWindows(true).catch(() => ({ total: 0 })),
        getFileAccessStats().catch(() => ({ flagged_count: 0 })),
        getAgentStats().catch(() => null),
        listAgentRuns({ limit: 5 }).catch(() => ({ items: [] })),
      ])
      setGovStats({
        pending: pc.total ?? 0,
        overdue: att.total ?? 0,
        flagged: fa.flagged_count ?? 0,
        freezes: fw.total ?? 0,
      })
      setAgentStats(as)
      setAgentRuns(ar.items ?? [])
    } catch {
      // keep page rendering even if these fail
    }
  }, [])

  useEffect(() => { load() }, [load])

  const s = stats ?? MOCK_STATS
  const depts = s.departments ?? []
  const maxDept = depts.length ? Math.max(...depts.map(d => d.count)) : 1
  const risks = s.risk_distribution ?? {}
  const riskTotal = Object.values(risks).reduce((a, b) => a + (b || 0), 0)
  const deptCount = depts.length

  const unverified = s.unverified_rules ?? 0
  const activePct  = s.total_rules ? Math.round((s.active_rules / s.total_rules) * 100) : 0

  return (
    <>
      <header className="page-head">
        <div>
          <div className="folio">§ I · Overview</div>
          <h1>Overview <em>— state of the registry</em></h1>
          <div className="lede">
            {s.total_rules ?? '—'} automation rules across {deptCount} departments. {unverified} await verification; {s.recent_changes ?? 0} amended in the last 24 hours.
          </div>
        </div>
        <div className="head-actions">
          <button className="btn sm" onClick={load} disabled={loading}>
            {Ic.refresh} Refresh
          </button>
          <button className="btn sm primary" onClick={() => navigate('/registry')}>
            {Ic.plus} New rule
          </button>
        </div>
      </header>

      {unverified > 0 && (
        <div className="banner">
          <div className="banner-ico">{Ic.bell}</div>
          <div style={{ flex: 1 }}>
            <div className="banner-t">{unverified} rules await verification</div>
            <div className="banner-d">Stewards should review and sign these before the next drift scan.</div>
          </div>
          <div className="right">
            <button className="btn sm">Dismiss</button>
            <button className="btn sm accent" onClick={() => navigate('/registry?verified=false')}>
              Review now {Ic.arrow}
            </button>
          </div>
        </div>
      )}

      <div className="kpi-row">
        <button className="kpi click" onClick={() => navigate('/registry')}>
          <div className="label">{Ic.list} Total rules</div>
          <div className="num-big num">{s.total_rules ?? '—'}</div>
          <div className="caption">enrolled in registry</div>
          <div className="folio-mark">i</div>
        </button>
        <button className="kpi ok click" onClick={() => navigate('/registry?status=active')}>
          <div className="label">{Ic.check} Active</div>
          <div className="num-big num">{s.active_rules ?? '—'}</div>
          <div className="caption">{activePct}% running live</div>
          <div className="folio-mark">ii</div>
        </button>
        <button className="kpi warn click" onClick={() => navigate('/registry?verified=false')}>
          <div className="label">{Ic.bell} Need review</div>
          <div className="num-big num">{unverified}</div>
          <div className="caption">awaiting verification</div>
          <div className="folio-mark">iii</div>
        </button>
        <button className="kpi focus click" onClick={() => navigate('/audit')}>
          <div className="label">{Ic.log} Changes · 24h</div>
          <div className="num-big num">{s.recent_changes ?? 0}</div>
          <div className="caption">edits &amp; verifications</div>
          <div className="folio-mark">iv</div>
        </button>
      </div>

      {/* ---------- Governance health strip ---------- */}
      <div style={{ marginTop: 20, marginBottom: 8 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Governance health</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          <button className="l-card" onClick={() => navigate('/governance')}
                  style={{ padding: 14, textAlign: 'left', cursor: 'pointer', border: '1px solid var(--rule-soft)',
                           background: govStats.pending > 0 ? 'color-mix(in srgb, var(--warn) 6%, var(--vellum))' : 'var(--vellum)' }}>
            <div className="eyebrow">Pending approvals</div>
            <div className="num" style={{ fontSize: 22, marginTop: 2, color: govStats.pending > 0 ? 'var(--warn)' : 'var(--ink)' }}>
              {govStats.pending}
            </div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>
              {govStats.pending > 0 ? 'awaiting sign-off →' : 'queue clear'}
            </div>
          </button>
          <button className="l-card" onClick={() => navigate('/governance')}
                  style={{ padding: 14, textAlign: 'left', cursor: 'pointer', border: '1px solid var(--rule-soft)',
                           background: govStats.overdue > 0 ? 'color-mix(in srgb, var(--risk-high) 6%, var(--vellum))' : 'var(--vellum)' }}>
            <div className="eyebrow">Overdue attestations</div>
            <div className="num" style={{ fontSize: 22, marginTop: 2, color: govStats.overdue > 0 ? 'var(--risk-high)' : 'var(--ink)' }}>
              {govStats.overdue}
            </div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>
              {govStats.overdue > 0 ? 'past due date →' : 'on schedule'}
            </div>
          </button>
          <button className="l-card" onClick={() => navigate('/data-access?sensitivity=flagged')}
                  style={{ padding: 14, textAlign: 'left', cursor: 'pointer', border: '1px solid var(--rule-soft)',
                           background: govStats.flagged > 0 ? 'color-mix(in srgb, var(--risk-crit) 5%, var(--vellum))' : 'var(--vellum)' }}>
            <div className="eyebrow">Flagged files</div>
            <div className="num" style={{ fontSize: 22, marginTop: 2, color: govStats.flagged > 0 ? 'var(--risk-crit)' : 'var(--ink)' }}>
              {govStats.flagged}
            </div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>
              {govStats.flagged > 0 ? 'sensitive reads to review →' : 'no sensitive reads'}
            </div>
          </button>
          <button className="l-card" onClick={() => navigate('/governance')}
                  style={{ padding: 14, textAlign: 'left', cursor: 'pointer', border: '1px solid var(--rule-soft)' }}>
            <div className="eyebrow">Active freezes</div>
            <div className="num" style={{ fontSize: 22, marginTop: 2 }}>{govStats.freezes}</div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>
              {govStats.freezes > 0 ? 'edits blocked for scope →' : 'no windows active'}
            </div>
          </button>
        </div>
      </div>

      <div className="two-col">
        <div className="l-card">
          <div className="card-head">
            <div className="card-title">Rules by department</div>
            <div className="dim" style={{ fontSize: 12 }}>{s.total_rules ?? 0} total</div>
          </div>
          <div className="dept-list">
            {depts.map(d => (
              <div key={d.name} className="dept-row">
                <div className="n">{d.name}</div>
                <div className="track">
                  <div className="fill" style={{ width: `${(d.count / maxDept) * 100}%` }} />
                </div>
                <div className="cnt">{d.count}</div>
                <div className="pct">
                  {d.pct ?? (s.total_rules ? Math.round((d.count / s.total_rules) * 100) : 0)}%
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="l-card">
          <div className="card-head">
            <div className="card-title">Risk distribution</div>
            <div className="dim" style={{ fontSize: 12 }}>{riskTotal} rules</div>
          </div>
          <div className="dept-list">
            {RISK_ORDER.map(k => {
              const meta = RISK_META[k]
              const count = risks[k] ?? 0
              const pct = riskTotal ? Math.round((count / riskTotal) * 100) : 0
              return (
                <div key={k} className="dept-row">
                  <div className="n" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: meta.var }} />
                    {meta.tier}
                  </div>
                  <div className="track">
                    <div className="fill" style={{ width: `${pct * 2}%`, background: meta.var }} />
                  </div>
                  <div className="cnt">{count}</div>
                  <div className="pct">{pct}%</div>
                </div>
              )
            })}
          </div>
          <div className="risk-grid">
            {RISK_ORDER.map(k => {
              const meta = RISK_META[k]
              const count = risks[k] ?? 0
              return (
                <div key={k} className={`risk-tile ${meta.key}`}>
                  <div>
                    <div className="t">{meta.tier}</div>
                    <div className="c">{meta.caption}</div>
                  </div>
                  <div className="n num">{count}</div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="three-col mt24">
        <div className="l-card" style={{ gridColumn: '1 / span 2' }}>
          <div className="card-head">
            <div className="card-title">Recent activity</div>
            <button className="btn sm ghost" onClick={() => navigate('/audit')}>
              View all {Ic.arrow}
            </button>
          </div>
          <div>
            {(audit.length ? audit : MOCK_AUDIT).slice(0, 8).map(a => {
              // Plain-English action label + pill kind for non-sophisticated users
              const ACTION_META = {
                editable_update: { label: 'Edit',     kind: ''        },
                edit:            { label: 'Edit',     kind: ''        },
                status_change:   { label: 'Status',   kind: 'paused'  },
                verify:          { label: 'Verified', kind: 'active'  },
                created:         { label: 'Added',    kind: 'planned' },
                add:             { label: 'Added',    kind: 'planned' },
                approved:        { label: 'Approved', kind: 'active'  },
                rejected:        { label: 'Rejected', kind: 'paused'  },
                extraction_create: { label: 'Imported', kind: 'planned' },
                extraction_update: { label: 'Imported', kind: 'planned' },
                import:          { label: 'Imported', kind: 'planned' },
                delete:          { label: 'Removed',  kind: 'paused'  },
              }
              const meta = ACTION_META[a.action] || { label: 'Change', kind: '' }

              // Build a human-readable description from the structured fields
              // ("Raised threshold from 5000 to 7500") rather than showing raw IDs.
              function describeChange(entry) {
                if (entry.description) return entry.description
                const field = entry.field_name
                let oldV = entry.old_value, newV = entry.new_value
                const parse = (v) => {
                  if (v === null || v === undefined || v === '') return null
                  if (typeof v === 'string') {
                    try { return JSON.parse(v) } catch { return v }
                  }
                  return v
                }
                oldV = parse(oldV); newV = parse(newV)

                if (entry.action === 'verify' || entry.action === 'approved') return 'marked as verified'
                if (entry.action === 'rejected') return 'change was rejected'
                if (entry.action === 'status_change')   return `status → ${newV ?? 'changed'}`
                if (entry.action === 'extraction_create' || entry.action === 'extraction_update' || entry.action === 'created' || entry.action === 'add') {
                  return 'imported by extraction'
                }
                if (entry.action === 'editable_update' || entry.action === 'edit') {
                  if (field) {
                    const pretty = field.replace(/_/g, ' ')
                    if (oldV == null && newV != null)  return `set ${pretty} to ${JSON.stringify(newV)}`
                    if (oldV != null && newV == null)  return `cleared ${pretty}`
                    if (oldV != null && newV != null)  return `${pretty}: ${JSON.stringify(oldV)} → ${JSON.stringify(newV)}`
                  }
                  return 'edited a setting'
                }
                return 'made a change'
              }

              const title = a.rule_title || a.rule_id || 'Unknown rule'
              const desc = describeChange(a)
              const who = a.changed_by || a.operator || 'system'

              return (
                <div key={a.id ?? `${a.rule_id}-${a.timestamp}`} className="activity-item"
                     style={{ display: 'grid', gridTemplateColumns: '90px 90px 1fr auto', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--rule-hair)' }}>
                  <span className="when" style={{ fontSize: 11, color: 'var(--ink-4)', fontFamily: 'var(--ff-mono)' }}>
                    {formatWhen(a.timestamp)}
                  </span>
                  <div>
                    <Pill kind={meta.kind}>{meta.label}</Pill>
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {title}
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {desc}
                    </div>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--ink-4)' }}>
                    {who}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="health">
            <div className="card-head" style={{ marginBottom: 8 }}>
              <div className="card-title" style={{ fontSize: 15 }}>Extraction health</div>
              <Pill kind={s.extraction_health?.drift_status === 'drifted' ? 'paused' : 'active'}>
                {s.extraction_health?.drift_status === 'drifted' ? 'Drift'
                  : s.extraction_health?.drift_status === 'unknown' ? 'Unknown'
                  : 'Clean'}
              </Pill>
            </div>
            <div className="row">
              <div className="k">Last scan</div>
              <div className="v">{formatWhen(s.extraction_health?.last_scan)}</div>
            </div>
            <div className="row">
              <div className="k">Files scanned</div>
              <div className="v">{s.extraction_health?.files_scanned?.toLocaleString() ?? '—'}</div>
            </div>
            <button
              className="btn mt16"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => navigate('/extractions')}
            >
              {Ic.play} Run scan
            </button>
          </div>

          <div className="l-card" style={{ padding: '14px 18px' }}>
            <div className="card-head" style={{ marginBottom: 6 }}>
              <div className="card-title" style={{ fontSize: 15 }}>Agent activity</div>
              <button className="btn sm ghost" onClick={() => navigate('/agent-logs')}>
                View all {Ic.arrow}
              </button>
            </div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)', marginBottom: 8 }}>
              {agentStats ? (
                <>
                  <strong style={{ color: 'var(--ink-2)' }}>{agentStats.runs_last_24h}</strong> LLM call{agentStats.runs_last_24h !== 1 ? 's' : ''} in the last 24h
                  {agentStats.failed_count > 0 && (
                    <> · <strong style={{ color: 'var(--risk-crit)' }}>{agentStats.failed_count}</strong> failed</>
                  )}
                </>
              ) : 'No agent activity recorded yet.'}
            </div>
            {agentRuns.length === 0 ? (
              <div style={{ fontSize: 11, color: 'var(--ink-5)', fontStyle: 'italic', padding: '8px 0' }}>
                No runs yet.
              </div>
            ) : (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {agentRuns.slice(0, 5).map((r) => (
                  <li key={r.id} onClick={() => navigate('/agent-logs')}
                      style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0', borderTop: '1px solid var(--rule-hair)', cursor: 'pointer', fontSize: 11 }}>
                    <span className={`pill ${r.status === 'completed' ? 'active' : r.status === 'failed' ? 'crit' : 'planned'}`} style={{ fontSize: 9.5, padding: '1px 5px' }}>
                      {r.agent_name}
                    </span>
                    <span style={{ flex: 1, color: 'var(--ink-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.step_label || '(unlabeled)'}
                    </span>
                    <span style={{ color: 'var(--ink-4)', fontFamily: 'var(--ff-mono)' }}>
                      {r.duration_ms != null ? (r.duration_ms < 1000 ? `${r.duration_ms}ms` : `${(r.duration_ms/1000).toFixed(1)}s`) : '—'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="l-card" style={{ padding: '14px 18px' }}>
            <div className="card-title" style={{ fontSize: 15, marginBottom: 6 }}>Quick actions</div>
            <ul className="qa-list">
              <li onClick={() => navigate('/registry?verified=false')}>
                <span className="qa-ico">{Ic.bell}</span>
                <div>
                  <span className="qa-t">Review unverified</span>
                  <span className="qa-d">{unverified} pending signoff</span>
                </div>
                <span className="qa-ar">{Ic.arrow}</span>
              </li>
              <li onClick={() => navigate('/registry?risk_level=critical')}>
                <span className="qa-ico">{Ic.list}</span>
                <div>
                  <span className="qa-t">High-risk rules</span>
                  <span className="qa-d">{(risks.critical ?? 0) + (risks.high ?? 0)} critical &amp; high</span>
                </div>
                <span className="qa-ar">{Ic.arrow}</span>
              </li>
              <li onClick={() => navigate('/graph')}>
                <span className="qa-ico">{Ic.flow}</span>
                <div>
                  <span className="qa-t">Process graph</span>
                  <span className="qa-d">explore dependencies</span>
                </div>
                <span className="qa-ar">{Ic.arrow}</span>
              </li>
              <li onClick={() => navigate('/extractions')}>
                <span className="qa-ico">{Ic.scan}</span>
                <div>
                  <span className="qa-t">New extraction</span>
                  <span className="qa-d">scan source</span>
                </div>
                <span className="qa-ar">{Ic.arrow}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </>
  )
}
