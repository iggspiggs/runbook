import React, { useCallback, useEffect, useState } from 'react'
import {
  listPendingChanges, decidePendingChange, cancelPendingChange,
  listFreezeWindows, createFreezeWindow, deleteFreezeWindow,
  listAttestations, issueAttestationCampaign, respondAttestation,
} from '../../api/client.js'
import { useCurrentUser } from '../../stores/currentUser.js'

const Ic = {
  clock:   <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/></svg>,
  calendar:<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="2" y="3.5" width="12" height="10" rx="1"/><path d="M2 6.5h12M5 2v2M11 2v2"/></svg>,
  pen:     <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M10 3l3 3-7 7H3v-3l7-7z"/></svg>,
  plus:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 3v10M3 8h10"/></svg>,
  refresh: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M13 7a5 5 0 1 0-1.5 3.5M13 3v3h-3"/></svg>,
  check:   <svg width="13" height="13" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M2 6.5l2.5 2.5L10 3.5"/></svg>,
  x:       <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 4l8 8M12 4l-8 8"/></svg>,
  trash:   <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M3 4h10M6 4V3a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1M4.5 4l.8 9a1 1 0 0 0 1 1h3.4a1 1 0 0 0 1-1l.8-9"/></svg>,
  warn:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M8 2l6.5 11H1.5L8 2zM8 6v3M8 11v.01"/></svg>,
}

const TABS = [
  { key: 'approvals',    label: 'Approvals',       ico: Ic.clock    },
  { key: 'attestations', label: 'Attestations',    ico: Ic.pen      },
  { key: 'freezes',      label: 'Freeze Windows',  ico: Ic.calendar },
]

const RISK_PILL = { critical: 'crit', high: 'high', medium: 'med', low: 'low' }

function fmt(iso) {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(iso))
  } catch { return iso }
}

function relative(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const absMin = Math.abs(diff) / 60_000
  const sign = diff > 0 ? '' : 'in '
  const ago = diff > 0 ? ' ago' : ''
  if (absMin < 1) return 'just now'
  if (absMin < 60) return `${sign}${Math.round(absMin)}m${ago}`
  const h = absMin / 60
  if (h < 24) return `${sign}${Math.round(h)}h${ago}`
  const d = h / 24
  if (d < 14) return `${sign}${Math.round(d)}d${ago}`
  return fmt(iso)
}

// ============================================================== Approvals tab
function ApprovalsTab() {
  const { currentUser } = useCurrentUser()
  const [items, setItems] = useState([])
  const [statusFilter, setStatusFilter] = useState('pending')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await listPendingChanges({ status: statusFilter === 'all' ? undefined : statusFilter })
      setItems(r.items ?? [])
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  const handleDecide = async (id, decision, note) => {
    try { await decidePendingChange(id, decision, note); load() }
    catch (e) { setError(e.message) }
  }
  const handleCancel = async (id) => {
    try { await cancelPendingChange(id); load() }
    catch (e) { setError(e.message) }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14, alignItems: 'center' }}>
        {['pending', 'applied', 'rejected', 'expired', 'cancelled', 'all'].map((s) => (
          <button key={s} onClick={() => setStatusFilter(s)}
                  className={`btn sm ${statusFilter === s ? 'primary' : 'ghost'}`}
                  style={{ textTransform: 'capitalize' }}>
            {s}
          </button>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--ink-4)' }}>
          {items.length} {statusFilter === 'all' ? 'total' : statusFilter}
        </span>
        <button className="btn sm ghost" onClick={load} disabled={loading}>{Ic.refresh}<span>Refresh</span></button>
      </div>

      {error && <div className="pill crit" style={{ marginBottom: 8 }}>{Ic.warn}<span>{error}</span></div>}
      {items.length === 0 && !loading && (
        <div className="l-card" style={{ padding: 28, textAlign: 'center', color: 'var(--ink-4)', fontSize: 13 }}>
          No changes in this view. Edits to high/critical-risk rules queue here for approval.
        </div>
      )}

      {items.map((pc) => (
        <PendingChangeCard
          key={pc.id} pc={pc}
          currentUser={currentUser}
          onDecide={handleDecide}
          onCancel={handleCancel}
        />
      ))}
    </div>
  )
}

function PendingChangeCard({ pc, currentUser, onDecide, onCancel }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const isRequester = currentUser?.id === pc.requested_by
  const canApprove = currentUser?.roles?.some((r) => r === 'approver' || r === 'admin')
  const alreadyVoted = (pc.approvals || []).some((a) => a.approver_id === currentUser?.id)
  const approvesCount = (pc.approvals || []).filter((a) => a.decision === 'approve').length
  const riskClass = RISK_PILL[pc.rule_risk_level]

  const submit = async (decision) => {
    setBusy(true)
    try { await onDecide(pc.id, decision, note); setNote('') }
    finally { setBusy(false) }
  }

  const statusPill = pc.status === 'pending' ? 'paused'
    : pc.status === 'applied' ? 'active'
    : pc.status === 'rejected' ? 'crit' : 'planned'

  return (
    <div className="l-card" style={{ padding: 16, marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'baseline', marginBottom: 6 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 className="display" style={{ fontSize: 18, margin: 0 }}>{pc.rule_title ?? pc.rule_id}</h3>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
            <span className={`pill ${statusPill}`}><span className="dot" />{pc.status}</span>
            {riskClass && <span className={`pill ${riskClass}`}>{pc.rule_risk_level} risk</span>}
          </div>
        </div>
        <div style={{ textAlign: 'right', fontSize: 11.5, color: 'var(--ink-4)' }}>
          <div>Requested {relative(pc.requested_at)}</div>
          {pc.expires_at && pc.status === 'pending' && (
            <div>Expires {relative(pc.expires_at)}</div>
          )}
        </div>
      </div>

      <div style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 8 }}>
        by <strong>{pc.requested_by_email}</strong>
        {pc.ticket_ref && <> · <code className="mono" style={{ background: 'var(--paper-2)', padding: '1px 4px', borderRadius: 3 }}>{pc.ticket_ref}</code></>}
      </div>

      {pc.reason && (
        <p style={{ fontSize: 12.5, color: 'var(--ink-2)', fontStyle: 'italic', margin: '0 0 10px', padding: '8px 10px', background: 'var(--paper-2)', borderLeft: '2px solid var(--rule)' }}>
          "{pc.reason}"
        </p>
      )}

      <div style={{ background: 'var(--paper-2)', border: '1px solid var(--rule-soft)', borderRadius: 'var(--radius)', padding: 10, marginBottom: 10 }}>
        <div className="eyebrow" style={{ marginBottom: 4 }}>Proposed changes</div>
        <pre className="mono" style={{ fontSize: 11.5, color: 'var(--ink-2)', margin: 0, whiteSpace: 'pre-wrap' }}>
{JSON.stringify(pc.changes, null, 2)}
        </pre>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--ink-3)', marginBottom: 8 }}>
        <span><strong>{approvesCount}</strong> / {pc.approvals_required} approval{pc.approvals_required !== 1 && 's'}</span>
        <span style={{ color: 'var(--ink-4)' }}>{(pc.approvals || []).length} vote{(pc.approvals || []).length !== 1 && 's'}</span>
      </div>

      {(pc.approvals || []).length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 10px', borderTop: '1px solid var(--rule-hair)' }}>
          {pc.approvals.map((a) => (
            <li key={a.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--rule-hair)', fontSize: 11.5 }}>
              <span style={{ color: a.decision === 'approve' ? 'var(--ok)' : 'var(--risk-crit)' }}>
                {a.decision === 'approve' ? Ic.check : Ic.x}
              </span>
              <strong>{a.approver_email}</strong>
              <span style={{ color: 'var(--ink-4)' }}>{relative(a.decided_at)}</span>
              {a.note && <span style={{ color: 'var(--ink-3)', fontStyle: 'italic' }}>— {a.note}</span>}
            </li>
          ))}
        </ul>
      )}

      {pc.status === 'pending' && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', paddingTop: 10, borderTop: '1px solid var(--rule-hair)', flexWrap: 'wrap' }}>
          <div className="input" style={{ flex: 1, minWidth: 220 }}>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note on your decision…" />
          </div>
          {canApprove && !isRequester && !alreadyVoted && (
            <>
              <button className="btn primary" disabled={busy} onClick={() => submit('approve')}>{Ic.check}<span>Approve</span></button>
              <button className="btn" disabled={busy} onClick={() => submit('reject')} style={{ color: 'var(--risk-crit)', borderColor: 'var(--risk-crit)' }}>{Ic.x}<span>Reject</span></button>
            </>
          )}
          {isRequester && (
            <button className="btn ghost" disabled={busy} onClick={() => onCancel(pc.id)}>Cancel</button>
          )}
          {!canApprove && !isRequester && (
            <span style={{ fontSize: 11, color: 'var(--ink-4)' }}>approver/admin role needed</span>
          )}
          {alreadyVoted && <span style={{ fontSize: 11, color: 'var(--ink-4)' }}>you've already voted</span>}
          {isRequester && canApprove && (
            <span style={{ fontSize: 11, color: 'var(--ink-4)' }}>can't approve your own</span>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================ Attestations tab
function AttestationsTab() {
  const { currentUser } = useCurrentUser()
  const isAdmin = currentUser?.roles?.includes('admin')
  const [items, setItems] = useState([])
  const [filter, setFilter] = useState('pending')
  const [error, setError] = useState(null)
  const [showCampaign, setShowCampaign] = useState(false)
  const [campaignForm, setCampaignForm] = useState({
    period_label: (() => {
      const n = new Date()
      return `${n.getFullYear()}-Q${Math.floor(n.getMonth() / 3) + 1}`
    })(),
    due_in_days: 14,
  })

  const load = useCallback(async () => {
    try {
      const r = await listAttestations({ status: filter === 'all' ? undefined : filter })
      setItems(r.items ?? [])
    } catch (e) { setError(e.message) }
  }, [filter])
  useEffect(() => { load() }, [load])

  const runCampaign = async () => {
    try {
      const r = await issueAttestationCampaign(campaignForm)
      alert(`Created ${r.created} attestations (${r.skipped} skipped as duplicates) for ${r.period_label}.`)
      setShowCampaign(false)
      load()
    } catch (e) { setError(e.message) }
  }

  const respond = async (id, status, note) => {
    try { await respondAttestation(id, { status, note }); load() }
    catch (e) { setError(e.message) }
  }

  const counts = {
    pending:  items.filter((a) => a.status === 'pending').length,
    overdue:  items.filter((a) => a.status === 'overdue').length,
    attested: items.filter((a) => a.status === 'attested').length,
  }

  return (
    <div>
      <div className="kpi-row" style={{ marginBottom: 14 }}>
        <div className="kpi"><div className="label">Pending</div><div className="num">{counts.pending}</div></div>
        <div className="kpi">
          <div className="label" style={{ color: counts.overdue ? 'var(--risk-high)' : 'var(--ink-3)' }}>Overdue</div>
          <div className="num" style={{ color: counts.overdue ? 'var(--risk-high)' : 'var(--ink)' }}>{counts.overdue}</div>
        </div>
        <div className="kpi">
          <div className="label" style={{ color: 'var(--ok)' }}>Attested</div>
          <div className="num" style={{ color: 'var(--ok)' }}>{counts.attested}</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
        {['pending', 'overdue', 'attested', 'changes_needed', 'all'].map((s) => (
          <button key={s} className={`btn sm ${filter === s ? 'primary' : 'ghost'}`} onClick={() => setFilter(s)}
                  style={{ textTransform: 'capitalize' }}>
            {s.replace('_', ' ')}
          </button>
        ))}
        {isAdmin && (
          <button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => setShowCampaign((v) => !v)}>
            {Ic.plus}<span>New campaign</span>
          </button>
        )}
      </div>

      {showCampaign && (
        <div className="l-card" style={{ padding: 14, marginBottom: 12 }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Issue attestation campaign</div>
          <p style={{ fontSize: 12, color: 'var(--ink-3)', margin: '0 0 10px' }}>
            Creates one attestation per rule. Idempotent — duplicates within the same period label are skipped.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: 10 }}>
            <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Period label
              <div className="input" style={{ marginTop: 4 }}>
                <input value={campaignForm.period_label}
                       onChange={(e) => setCampaignForm({ ...campaignForm, period_label: e.target.value })} />
              </div>
            </label>
            <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Due in (days)
              <div className="input" style={{ marginTop: 4 }}>
                <input type="number" min="1" max="365" value={campaignForm.due_in_days}
                       onChange={(e) => setCampaignForm({ ...campaignForm, due_in_days: +e.target.value })} />
              </div>
            </label>
          </div>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', marginTop: 10 }}>
            <button className="btn sm ghost" onClick={() => setShowCampaign(false)}>Cancel</button>
            <button className="btn sm primary" onClick={runCampaign}>Issue</button>
          </div>
        </div>
      )}

      {error && <div className="pill crit" style={{ marginBottom: 8 }}>{Ic.warn}<span>{error}</span></div>}
      {items.length === 0 && (
        <div className="l-card" style={{ padding: 28, textAlign: 'center', color: 'var(--ink-4)', fontSize: 13 }}>
          {filter === 'pending' ? 'No pending attestations.' : `No attestations in '${filter}'.`}
        </div>
      )}

      {items.map((a) => (
        <AttestationRow key={a.id} att={a} currentUser={currentUser} onRespond={respond} />
      ))}
    </div>
  )
}

function AttestationRow({ att, currentUser, onRespond }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const canRespond = att.status === 'pending' || att.status === 'overdue'
  const isOwner = currentUser?.email?.toLowerCase() === (att.owner_email || '').toLowerCase()

  const statusPill = att.status === 'overdue' ? 'crit'
    : att.status === 'attested' ? 'active'
    : att.status === 'changes_needed' ? 'paused'
    : 'planned'

  return (
    <div className="l-card" style={{ padding: 12, marginBottom: 8 }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', cursor: canRespond ? 'pointer' : 'default' }}
           onClick={() => canRespond && setOpen((v) => !v)}>
        <span className={`pill ${statusPill}`}><span className="dot" />{att.status.replace('_', ' ')}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 500, fontSize: 13.5, color: 'var(--ink)' }}>{att.rule_title}</div>
          <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 2 }}>
            {att.period_label} · due {relative(att.due_at)} · owner: <strong>{att.owner_email}</strong>
            {att.responded_by_email && <> · responded by {att.responded_by_email} {relative(att.responded_at)}</>}
          </div>
        </div>
      </div>

      {open && canRespond && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--rule-hair)' }}>
          {!isOwner && (
            <div style={{ fontSize: 11, color: 'var(--warn)', marginBottom: 6 }}>
              Note: the owner of record is {att.owner_email}. Responding as someone else is allowed but recorded.
            </div>
          )}
          <div className="input" style={{ marginBottom: 8 }}>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)…" />
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn sm primary" onClick={() => onRespond(att.id, 'attested', note)}>{Ic.check}<span>Attest — still correct</span></button>
            <button className="btn sm" style={{ color: 'var(--warn)', borderColor: 'var(--warn)' }}
                    onClick={() => onRespond(att.id, 'changes_needed', note)}>
              Needs changes
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================== Freezes tab
function FreezesTab() {
  const { currentUser } = useCurrentUser()
  const isAdmin = currentUser?.roles?.includes('admin')
  const [freezes, setFreezes] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try { setFreezes((await listFreezeWindows(false)).items ?? []) }
    catch (e) { setError(e.message) }
  }, [])
  useEffect(() => { load() }, [load])

  const deleteIt = async (id) => {
    try { await deleteFreezeWindow(id); load() }
    catch (e) { setError(e.message) }
  }

  return (
    <div>
      {isAdmin && !showForm && (
        <button className="btn primary" style={{ marginBottom: 12 }} onClick={() => setShowForm(true)}>
          {Ic.plus}<span>New freeze window</span>
        </button>
      )}

      {showForm && <FreezeForm onCreated={() => { setShowForm(false); load() }} onCancel={() => setShowForm(false)} />}

      {error && <div className="pill crit" style={{ marginBottom: 8 }}>{Ic.warn}<span>{error}</span></div>}
      {freezes.length === 0 && (
        <div className="l-card" style={{ padding: 28, textAlign: 'center', color: 'var(--ink-4)', fontSize: 13 }}>
          No freeze windows configured.
        </div>
      )}
      {freezes.map((f) => {
        const inEffect = f.active && new Date(f.start_at) <= new Date() && new Date(f.end_at) >= new Date()
        return (
          <div key={f.id} className="l-card" style={{
            padding: 14, marginBottom: 8,
            borderLeft: inEffect ? '3px solid var(--risk-crit)' : '3px solid transparent',
            opacity: f.active ? 1 : 0.55,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <h3 className="display" style={{ fontSize: 16, margin: 0 }}>{f.name}</h3>
                  {inEffect && <span className="pill crit"><span className="dot" />active now</span>}
                  {!f.active && <span className="pill planned">inactive</span>}
                </div>
                {f.description && <p style={{ fontSize: 12, color: 'var(--ink-3)', margin: '4px 0 0' }}>{f.description}</p>}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginTop: 8, fontSize: 11.5, color: 'var(--ink-3)' }}>
                  <div><span className="eyebrow" style={{ display: 'inline' }}>Start </span>{fmt(f.start_at)}</div>
                  <div><span className="eyebrow" style={{ display: 'inline' }}>End </span>{fmt(f.end_at)}</div>
                  <div><span className="eyebrow" style={{ display: 'inline' }}>Scope </span>{f.scope}{f.scope_values.length ? ` (${f.scope_values.join(', ')})` : ''}</div>
                  <div><span className="eyebrow" style={{ display: 'inline' }}>Bypass </span>{f.bypass_roles.length ? f.bypass_roles.join(', ') : 'none'}</div>
                </div>
              </div>
              {isAdmin && f.active && (
                <button className="btn sm ghost" onClick={() => deleteIt(f.id)}>{Ic.trash}</button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function FreezeForm({ onCreated, onCancel }) {
  const [f, setF] = useState({
    name: '', description: '',
    start_at: new Date(Date.now() - 3_600_000).toISOString().slice(0, 16),
    end_at: new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 16),
    scope: 'by_tag',
    scope_values: 'billing',
    bypass_roles: ['admin'],
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const toggle = (role) =>
    setF({ ...f, bypass_roles: f.bypass_roles.includes(role) ? f.bypass_roles.filter((r) => r !== role) : [...f.bypass_roles, role] })

  const submit = async () => {
    setBusy(true); setError(null)
    try {
      await createFreezeWindow({
        name: f.name, description: f.description,
        start_at: new Date(f.start_at).toISOString(),
        end_at: new Date(f.end_at).toISOString(),
        scope: f.scope,
        scope_values: f.scope === 'all' ? [] : f.scope_values.split(',').map((s) => s.trim()).filter(Boolean),
        bypass_roles: f.bypass_roles,
        active: true,
      })
      onCreated()
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="l-card" style={{ padding: 14, marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <div className="eyebrow">New freeze window</div>
        <button className="btn sm ghost" onClick={onCancel}>{Ic.x}</button>
      </div>
      <div style={{ display: 'grid', gap: 10 }}>
        <div className="input"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Name (e.g. Month-end billing freeze)" /></div>
        <div className="input"><input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="Description" /></div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            Start
            <div className="input" style={{ marginTop: 4 }}>
              <input type="datetime-local" value={f.start_at} onChange={(e) => setF({ ...f, start_at: e.target.value })} />
            </div>
          </label>
          <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            End
            <div className="input" style={{ marginTop: 4 }}>
              <input type="datetime-local" value={f.end_at} onChange={(e) => setF({ ...f, end_at: e.target.value })} />
            </div>
          </label>
        </div>
        <label style={{ fontSize: 11, color: 'var(--ink-3)' }}>
          Scope
          <select value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })}
                  style={{ display: 'block', width: '100%', marginTop: 4, fontSize: 12, padding: '5px 8px', border: '1px solid var(--rule)', background: 'var(--vellum)', borderRadius: 4 }}>
            <option value="all">All rules</option>
            <option value="by_tag">By tag</option>
            <option value="by_risk">By risk level</option>
            <option value="by_department">By department</option>
          </select>
        </label>
        {f.scope !== 'all' && (
          <div className="input">
            <input value={f.scope_values} onChange={(e) => setF({ ...f, scope_values: e.target.value })}
                   placeholder={f.scope === 'by_tag' ? 'billing, finance' : f.scope === 'by_risk' ? 'high, critical' : 'Finance, Ops'} />
          </div>
        )}
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Bypass roles</div>
          <div style={{ display: 'flex', gap: 6 }}>
            {['editor', 'approver', 'admin'].map((r) => (
              <button key={r} className={`btn sm ${f.bypass_roles.includes(r) ? 'primary' : 'ghost'}`} onClick={() => toggle(r)}>
                {r}
              </button>
            ))}
          </div>
        </div>
        {error && <div className="pill crit">{Ic.warn}<span>{error}</span></div>}
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
          <button className="btn sm ghost" onClick={onCancel}>Cancel</button>
          <button className="btn sm primary" disabled={!f.name || busy} onClick={submit}>Create</button>
        </div>
      </div>
    </div>
  )
}

// ============================================================== Main page
export default function GovernancePage() {
  const [tab, setTab] = useState('approvals')

  return (
    <div>
      <div className="page-head">
        <div className="folio">V</div>
        <h1 className="display">Governance</h1>
        <p className="lede">
          Approval queue for risky edits, periodic owner attestations, and calendar-based change freezes.
          Every edit runs through permission → reason policy → freeze check → approval routing.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--rule)', marginBottom: 16 }}>
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
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

      {tab === 'approvals'    && <ApprovalsTab />}
      {tab === 'attestations' && <AttestationsTab />}
      {tab === 'freezes'      && <FreezesTab />}
    </div>
  )
}
