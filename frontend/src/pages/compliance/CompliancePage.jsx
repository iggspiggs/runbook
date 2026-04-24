import React, { useCallback, useEffect, useState } from 'react'
import {
  getSoDAlerts,
  listEvidencePacks, generateEvidencePack,
  listScanPolicies, createScanPolicy, deleteScanPolicy,
  listRetentionPolicies, upsertRetentionPolicy, retentionDryRun, retentionApply,
  listLegalHolds, createLegalHold, releaseLegalHold,
} from '../../api/client.js'
import { useCurrentUser } from '../../stores/currentUser.js'

// ---------- tiny stroke icons (match App.jsx vocabulary) ----------
const Ic = {
  archive: <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="2" y="3" width="12" height="3" rx="0.5"/><path d="M3 6v7h10V6M6.5 9h3"/></svg>,
  sigma:   <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M12 3H4l4 5-4 5h8"/></svg>,
  scope:   <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="8" cy="8" r="5"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2"/></svg>,
  hourglass:<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M4 2h8M4 14h8M5 2v3l3 3 3-3V2M5 14v-3l3-3 3 3v3"/></svg>,
  lock:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="3.5" y="7" width="9" height="6.5" rx="0.8"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg>,
  refresh: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M13 7a5 5 0 1 0-1.5 3.5M13 3v3h-3"/></svg>,
  plus:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 3v10M3 8h10"/></svg>,
  trash:   <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M3 4h10M6 4V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1M4.5 4l.8 9a1 1 0 0 0 1 1h3.4a1 1 0 0 0 1-1l.8-9"/></svg>,
  dl:      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M8 2v8M5 7l3 3 3-3M3 13h10"/></svg>,
  warn:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M8 2l6.5 11H1.5L8 2zM8 6v3M8 11v.01"/></svg>,
}

const TABS = [
  { key: 'evidence',   label: 'Evidence Packs',  ico: Ic.archive },
  { key: 'sod',        label: 'SoD Alerts',      ico: Ic.sigma   },
  { key: 'scan',       label: 'Scan Policies',   ico: Ic.scope   },
  { key: 'retention',  label: 'Retention & Holds', ico: Ic.hourglass },
]

const RETENTION_CATEGORIES = [
  { value: 'audit_logs',        label: 'Audit log'        },
  { value: 'file_access_logs',  label: 'File access log'  },
  { value: 'pending_changes',   label: 'Pending changes'  },
  { value: 'extraction_results',label: 'Extraction results' },
]

function fmt(iso) {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

function bytes(n) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

// ---------- Evidence Packs tab ----------
function EvidenceTab() {
  const [packs, setPacks] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({
    label: `Quarterly evidence — ${new Date().toISOString().slice(0, 7)}`,
    date_from: new Date(Date.now() - 90 * 86_400_000).toISOString().slice(0, 10),
    date_to: new Date().toISOString().slice(0, 10),
    tags: '',
    risk_levels: '',
  })

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setPacks((await listEvidencePacks()).items ?? []) }
    catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const generate = async () => {
    setLoading(true); setError(null)
    try {
      const body = {
        label: form.label,
        date_from: form.date_from ? new Date(form.date_from).toISOString() : null,
        date_to: form.date_to ? new Date(form.date_to + 'T23:59:59').toISOString() : null,
        filters: {
          tags: form.tags.split(',').map((s) => s.trim()).filter(Boolean),
          risk_levels: form.risk_levels.split(',').map((s) => s.trim()).filter(Boolean),
        },
      }
      const { blob, filename } = await generateEvidencePack(body)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename; a.click()
      URL.revokeObjectURL(url)
      load()
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="l-card" style={{ padding: 16, marginBottom: 16 }}>
        <div className="eyebrow">Generate new pack</div>
        <p style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 4 }}>
          Bundles rules, audit log, pending changes, freeze windows, and attestations for a date range.
          SHA-256 hash recorded for tamper evidence.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            Label
            <div className="input" style={{ marginTop: 4 }}>
              <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
            </div>
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <label style={{ fontSize: 11, color: 'var(--ink-3)', flex: 1 }}>
              From
              <div className="input" style={{ marginTop: 4 }}>
                <input type="date" value={form.date_from} onChange={(e) => setForm({ ...form, date_from: e.target.value })} />
              </div>
            </label>
            <label style={{ fontSize: 11, color: 'var(--ink-3)', flex: 1 }}>
              To
              <div className="input" style={{ marginTop: 4 }}>
                <input type="date" value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} />
              </div>
            </label>
          </div>
          <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            Filter by tags (comma-sep, optional)
            <div className="input" style={{ marginTop: 4 }}>
              <input value={form.tags} placeholder="billing, finance" onChange={(e) => setForm({ ...form, tags: e.target.value })} />
            </div>
          </label>
          <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            Filter by risk (comma-sep, optional)
            <div className="input" style={{ marginTop: 4 }}>
              <input value={form.risk_levels} placeholder="high, critical" onChange={(e) => setForm({ ...form, risk_levels: e.target.value })} />
            </div>
          </label>
        </div>

        <div style={{ marginTop: 12 }}>
          <button className="btn primary" disabled={loading} onClick={generate}>
            {Ic.dl}<span>Generate & download</span>
          </button>
        </div>
      </div>

      <div className="eyebrow" style={{ marginBottom: 8 }}>Previous packs</div>
      {error && <div className="pill" style={{ background: 'color-mix(in srgb, var(--warn) 12%, var(--vellum))', color: 'var(--warn)', marginBottom: 8 }}>{Ic.warn}<span>{error}</span></div>}
      {packs.length === 0 && (
        <div className="l-card" style={{ padding: 24, textAlign: 'center', color: 'var(--ink-4)', fontSize: 13 }}>
          No evidence packs yet.
        </div>
      )}
      {packs.map((p) => (
        <div key={p.id} className="l-card" style={{ padding: 14, marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <h3 className="display" style={{ fontSize: 15, margin: 0 }}>{p.label}</h3>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <span><strong>{p.rule_count}</strong> rules</span>
                <span><strong>{p.audit_count}</strong> audit entries</span>
                <span><strong>{p.approval_count}</strong> approvals</span>
                <span>{bytes(p.size_bytes)}</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 4 }}>
                by <strong>{p.requested_by_email}</strong> on {fmt(p.generated_at)}
              </div>
            </div>
            {p.sha256 && (
              <div style={{ textAlign: 'right' }}>
                <div className="eyebrow" style={{ fontSize: 9 }}>SHA-256</div>
                <code className="mono" style={{ fontSize: 10, color: 'var(--ink-4)' }}>
                  {p.sha256.slice(0, 16)}…
                </code>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------- SoD Alerts tab ----------
function SoDTab() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lookback, setLookback] = useState(30)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setAlerts((await getSoDAlerts({ lookback_days: lookback })).items ?? []) }
    catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [lookback])

  useEffect(() => { load() }, [load])

  const counts = {
    critical: alerts.filter((a) => a.severity === 'critical').length,
    high:     alerts.filter((a) => a.severity === 'high').length,
    medium:   alerts.filter((a) => a.severity === 'medium').length,
  }

  const SIG_LABEL = {
    self_approved:       'Self-approval',
    single_approver_bulk:'Bulk approval',
    maker_is_owner:      'Maker is owner',
    requester_verified:  'Self-verified',
  }

  const sevPill = { critical: 'crit', high: 'high', medium: 'med' }

  return (
    <div>
      <div className="kpi-row" style={{ marginBottom: 14 }}>
        <div className="kpi">
          <div className="label" style={{ color: counts.critical ? 'var(--risk-crit)' : 'var(--ink-3)' }}>Critical</div>
          <div className="num" style={{ color: counts.critical ? 'var(--risk-crit)' : 'var(--ink)' }}>{counts.critical}</div>
        </div>
        <div className="kpi">
          <div className="label" style={{ color: counts.high ? 'var(--risk-high)' : 'var(--ink-3)' }}>High</div>
          <div className="num" style={{ color: counts.high ? 'var(--risk-high)' : 'var(--ink)' }}>{counts.high}</div>
        </div>
        <div className="kpi">
          <div className="label" style={{ color: 'var(--ink-3)' }}>Medium</div>
          <div className="num">{counts.medium}</div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span className="eyebrow">Look back</span>
        {[7, 30, 90].map((d) => (
          <button key={d} className={`btn sm ${lookback === d ? 'primary' : 'ghost'}`} onClick={() => setLookback(d)}>
            {d}d
          </button>
        ))}
        <button className="btn sm ghost" onClick={load} disabled={loading} style={{ marginLeft: 'auto' }}>
          {Ic.refresh}<span>Refresh</span>
        </button>
      </div>

      {error && <div className="pill crit" style={{ marginBottom: 8 }}>{Ic.warn}<span>{error}</span></div>}
      {alerts.length === 0 && (
        <div className="l-card" style={{ padding: 28, textAlign: 'center', color: 'var(--ink-4)', fontSize: 13 }}>
          No anomalies detected in the last {lookback} days. Clean separation of duties.
        </div>
      )}
      {alerts.map((a, i) => (
        <div key={i} className="l-card" style={{
          padding: 14, marginBottom: 8,
          borderLeft: `3px solid ${a.severity === 'critical' ? 'var(--risk-crit)' : a.severity === 'high' ? 'var(--risk-high)' : 'var(--risk-med)'}`,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 4 }}>
            <h3 className="display" style={{ fontSize: 16, margin: 0 }}>{a.title}</h3>
            <span className={`pill ${sevPill[a.severity] || 'planned'}`}><span className="dot" />{a.severity}</span>
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--ink-3)', margin: '4px 0 8px', lineHeight: 1.5 }}>{a.detail}</p>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 11, color: 'var(--ink-4)', flexWrap: 'wrap' }}>
            <span className="pill planned" style={{ fontSize: 10 }}>{SIG_LABEL[a.signal] || a.signal}</span>
            {a.subject_email && <span>subject: <strong>{a.subject_email}</strong></span>}
            {a.occurred_at && <span>· {fmt(a.occurred_at)}</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------- Scan Policies tab ----------
function ScanPoliciesTab() {
  const { currentUser } = useCurrentUser()
  const isAdmin = currentUser?.roles?.includes('admin')
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    name: '', description: '', mode: 'deny',
    allow: '', deny: '**/secrets/**\n**/.env*\n**/*.pem',
  })

  const load = useCallback(async () => {
    try { setItems((await listScanPolicies()).items ?? []) }
    catch (e) { setError(e.message) }
  }, [])
  useEffect(() => { load() }, [load])

  const submit = async () => {
    setError(null)
    try {
      await createScanPolicy({
        name: form.name,
        description: form.description,
        mode: form.mode,
        allow_patterns: form.allow.split('\n').map((s) => s.trim()).filter(Boolean),
        deny_patterns: form.deny.split('\n').map((s) => s.trim()).filter(Boolean),
        active: true,
      })
      setShowForm(false)
      setForm({ ...form, name: '', description: '' })
      load()
    } catch (e) { setError(e.message) }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <p style={{ fontSize: 12, color: 'var(--ink-3)', margin: 0, maxWidth: 620 }}>
          Glob patterns checked before the extraction agent opens a file. Denied paths never reach the LLM —
          they're recorded as <code className="mono">skipped_error</code> on the Data Access page.
        </p>
        {isAdmin && !showForm && (
          <button className="btn primary" onClick={() => setShowForm(true)}>{Ic.plus}<span>New policy</span></button>
        )}
      </div>

      {showForm && (
        <div className="l-card" style={{ padding: 14, marginBottom: 12 }}>
          <div style={{ display: 'grid', gap: 10 }}>
            <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Name
              <div className="input" style={{ marginTop: 4 }}>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                       placeholder="e.g. Acme Logistics default deny" />
              </div>
            </label>
            <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Description
              <div className="input" style={{ marginTop: 4 }}>
                <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              </div>
            </label>
            <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Mode
              <select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}
                      style={{ display: 'block', width: '100%', marginTop: 4, fontSize: 12, padding: '5px 8px', border: '1px solid var(--rule)', background: 'var(--vellum)', borderRadius: 4 }}>
                <option value="deny">Deny — block listed patterns, allow everything else</option>
                <option value="allow">Allow — only scan listed patterns</option>
                <option value="hybrid">Hybrid — deny first, then require allow match</option>
              </select>
            </label>
            <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Deny patterns (one per line)
              <textarea value={form.deny} onChange={(e) => setForm({ ...form, deny: e.target.value })}
                        rows={4} className="mono"
                        style={{ display: 'block', width: '100%', marginTop: 4, fontSize: 11.5, border: '1px solid var(--rule)', borderRadius: 4, padding: 8 }} />
            </label>
            {form.mode !== 'deny' && (
              <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
                Allow patterns (one per line)
                <textarea value={form.allow} onChange={(e) => setForm({ ...form, allow: e.target.value })}
                          rows={4} className="mono"
                          style={{ display: 'block', width: '100%', marginTop: 4, fontSize: 11.5, border: '1px solid var(--rule)', borderRadius: 4, padding: 8 }} />
              </label>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
              <button className="btn sm ghost" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn sm primary" disabled={!form.name} onClick={submit}>Create</button>
            </div>
          </div>
        </div>
      )}

      {error && <div className="pill">{Ic.warn}<span>{error}</span></div>}
      {items.length === 0 && (
        <div className="l-card" style={{ padding: 24, textAlign: 'center', color: 'var(--ink-4)', fontSize: 13 }}>
          No scan policies yet. {isAdmin && 'Add one to protect sensitive paths.'}
        </div>
      )}
      {items.map((p) => (
        <div key={p.id} className="l-card" style={{ padding: 14, marginBottom: 8, opacity: p.active ? 1 : 0.6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 600, fontSize: 13.5 }}>{p.name}</span>
                <span className="pill" style={{ textTransform: 'uppercase', fontSize: 10 }}>
                  <span className="dot" />{p.mode}
                </span>
                {!p.active && <span className="pill" style={{ fontSize: 10 }}>inactive</span>}
              </div>
              {p.description && <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 4 }}>{p.description}</p>}
              {p.deny_patterns.length > 0 && (
                <div style={{ marginTop: 6 }}>
                  <div style={{ fontSize: 10, color: 'var(--ink-4)', textTransform: 'uppercase', letterSpacing: 0.4 }}>Deny</div>
                  <div className="mono" style={{ fontSize: 11.5, color: 'var(--ink-2)' }}>{p.deny_patterns.join(' · ')}</div>
                </div>
              )}
              {p.allow_patterns.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <div style={{ fontSize: 10, color: 'var(--ink-4)', textTransform: 'uppercase', letterSpacing: 0.4 }}>Allow</div>
                  <div className="mono" style={{ fontSize: 11.5, color: 'var(--ink-2)' }}>{p.allow_patterns.join(' · ')}</div>
                </div>
              )}
            </div>
            {isAdmin && p.active && (
              <button className="btn sm ghost" onClick={() => deleteScanPolicy(p.id).then(load)}>
                {Ic.trash}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------- Retention + Legal Holds tab ----------
function RetentionTab() {
  const { currentUser } = useCurrentUser()
  const isAdmin = currentUser?.roles?.includes('admin')
  const [policies, setPolicies] = useState([])
  const [holds, setHolds] = useState([])
  const [dryRun, setDryRun] = useState(null)
  const [error, setError] = useState(null)
  const [holdForm, setHoldForm] = useState({ name: '', description: '', rule_ids: '', categories: '' })

  const load = useCallback(async () => {
    try {
      const [p, h] = await Promise.all([listRetentionPolicies(), listLegalHolds()])
      setPolicies(p.items ?? [])
      setHolds(h.items ?? [])
    } catch (e) { setError(e.message) }
  }, [])
  useEffect(() => { load() }, [load])

  const savePolicy = async (category, days) => {
    try {
      await upsertRetentionPolicy({ category, retention_days: +days, active: true })
      load()
    } catch (e) { setError(e.message) }
  }

  const runDryRun = async () => {
    try { setDryRun(await retentionDryRun()) }
    catch (e) { setError(e.message) }
  }

  const apply = async () => {
    if (!confirm('Permanently delete rows eligible under the active retention policies? Held records will be preserved.')) return
    try {
      const res = await retentionApply()
      alert(`Deleted: ${JSON.stringify(res.deleted_by_category)}`)
      runDryRun()
    } catch (e) { setError(e.message) }
  }

  const placeHold = async () => {
    try {
      await createLegalHold({
        name: holdForm.name,
        description: holdForm.description,
        rule_ids: holdForm.rule_ids.split(',').map((s) => s.trim()).filter(Boolean),
        categories: holdForm.categories.split(',').map((s) => s.trim()).filter(Boolean),
      })
      setHoldForm({ name: '', description: '', rule_ids: '', categories: '' })
      load()
    } catch (e) { setError(e.message) }
  }

  return (
    <div>
      <div className="eyebrow">Retention policies</div>
      <p style={{ fontSize: 12, color: 'var(--ink-3)', margin: '4px 0 12px' }}>
        Records older than the retention period are eligible for deletion. Legal holds always override.
      </p>

      <div className="l-card" style={{ padding: 14, marginBottom: 16 }}>
        {RETENTION_CATEGORIES.map((c) => {
          const p = policies.find((x) => x.category === c.value)
          return (
            <div key={c.value} style={{ display: 'grid', gridTemplateColumns: '180px 1fr auto', gap: 12, alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--rule-hair)' }}>
              <div style={{ fontWeight: 500, fontSize: 13 }}>{c.label}</div>
              <div style={{ fontSize: 12, color: 'var(--ink-4)' }}>
                {p ? `${p.retention_days} days` : 'no policy — keep forever'}
              </div>
              {isAdmin && (
                <div style={{ display: 'flex', gap: 6 }}>
                  {[90, 365, 730, 2555].map((d) => (
                    <button key={d} className={`btn sm ${p?.retention_days === d ? 'primary' : 'ghost'}`}
                            onClick={() => savePolicy(c.value, d)}>
                      {d === 2555 ? '7y' : d === 730 ? '2y' : d === 365 ? '1y' : `${d}d`}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <button className="btn" onClick={runDryRun}>{Ic.refresh}<span>Dry run</span></button>
        {isAdmin && <button className="btn accent" onClick={apply}>{Ic.trash}<span>Apply deletion</span></button>}
      </div>

      {dryRun && (
        <div className="l-card" style={{ padding: 14, marginBottom: 20 }}>
          <div className="eyebrow">Dry-run preview</div>
          <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--ink-2)' }}>
            {Object.entries(dryRun.eligible_by_category || {}).map(([cat, n]) => (
              <div key={cat} style={{ padding: '4px 0' }}>
                <strong>{n}</strong> rows in <code className="mono">{cat}</code> would be deleted
                {dryRun.held_by_category?.[cat] > 0 && (
                  <span style={{ color: 'var(--ink-4)' }}>
                    {' '}(+ {dryRun.held_by_category[cat]} preserved by legal hold)
                  </span>
                )}
              </div>
            ))}
            {Object.keys(dryRun.eligible_by_category || {}).length === 0 && (
              <div style={{ color: 'var(--ink-4)' }}>Nothing eligible right now.</div>
            )}
          </div>
        </div>
      )}

      <div className="eyebrow">Legal holds</div>
      <p style={{ fontSize: 12, color: 'var(--ink-3)', margin: '4px 0 12px' }}>
        Freeze specific records from retention deletion during investigations or litigation.
      </p>

      {isAdmin && (
        <div className="l-card" style={{ padding: 14, marginBottom: 12 }}>
          <div style={{ display: 'grid', gap: 8 }}>
            <div className="input">
              <input value={holdForm.name} onChange={(e) => setHoldForm({ ...holdForm, name: e.target.value })}
                     placeholder="Hold name (e.g. 'Audit 2026 — SOX')" />
            </div>
            <div className="input">
              <input value={holdForm.description} onChange={(e) => setHoldForm({ ...holdForm, description: e.target.value })}
                     placeholder="Description" />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <div className="input" style={{ flex: 1 }}>
                <input value={holdForm.rule_ids} onChange={(e) => setHoldForm({ ...holdForm, rule_ids: e.target.value })}
                       placeholder="Rule IDs (comma-sep, optional)" />
              </div>
              <div className="input" style={{ flex: 1 }}>
                <input value={holdForm.categories} onChange={(e) => setHoldForm({ ...holdForm, categories: e.target.value })}
                       placeholder="Categories (audit_logs, file_access_logs, …)" />
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <button className="btn primary" disabled={!holdForm.name} onClick={placeHold}>{Ic.lock}<span>Place hold</span></button>
            </div>
          </div>
        </div>
      )}

      {holds.length === 0 && (
        <div className="l-card" style={{ padding: 24, textAlign: 'center', color: 'var(--ink-4)', fontSize: 13 }}>
          No legal holds placed.
        </div>
      )}
      {holds.map((h) => (
        <div key={h.id} className="l-card" style={{ padding: 14, marginBottom: 8, opacity: h.active ? 1 : 0.55 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <strong style={{ fontSize: 13.5 }}>{h.name}</strong>
                {h.active
                  ? <span className="pill"><span className="dot" style={{ background: 'var(--warn)' }} />active</span>
                  : <span className="pill">released</span>}
              </div>
              {h.description && <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 4 }}>{h.description}</p>}
              <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 4 }}>
                Placed by <strong>{h.placed_by_email}</strong> · {fmt(h.placed_at)}
                {h.rule_ids.length > 0 && <> · rules: <code className="mono">{h.rule_ids.join(', ')}</code></>}
                {h.categories.length > 0 && <> · categories: <code className="mono">{h.categories.join(', ')}</code></>}
              </div>
            </div>
            {isAdmin && h.active && (
              <button className="btn sm ghost" onClick={() => releaseLegalHold(h.id).then(load)}>Release</button>
            )}
          </div>
        </div>
      ))}

      {error && <div className="pill" style={{ marginTop: 12 }}>{Ic.warn}<span>{error}</span></div>}
    </div>
  )
}

// ---------- Main page ----------
export default function CompliancePage() {
  const [tab, setTab] = useState('evidence')

  return (
    <div>
      <div className="page-head">
        <div className="folio">VI</div>
        <h1 className="display">Compliance</h1>
        <p className="lede">
          Evidence packs for auditors, segregation-of-duties detection, scan-scope enforcement,
          retention policies, and legal holds — the controls that turn a live registry into a defensible one.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--rule)', marginBottom: 16 }}>
        {TABS.map((t) => (
          <button key={t.key}
                  onClick={() => setTab(t.key)}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '8px 14px', border: 'none', background: 'transparent',
                    fontSize: 13, cursor: 'pointer',
                    color: tab === t.key ? 'var(--ink)' : 'var(--ink-3)',
                    fontWeight: tab === t.key ? 600 : 400,
                    borderBottom: tab === t.key ? '2px solid var(--accent)' : '2px solid transparent',
                    marginBottom: -1,
                  }}>
            {t.ico}<span>{t.label}</span>
          </button>
        ))}
      </div>

      {tab === 'evidence'  && <EvidenceTab />}
      {tab === 'sod'       && <SoDTab />}
      {tab === 'scan'      && <ScanPoliciesTab />}
      {tab === 'retention' && <RetentionTab />}
    </div>
  )
}
