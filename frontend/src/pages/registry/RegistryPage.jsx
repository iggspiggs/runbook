import React, { useEffect, useState, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import useRegistryStore from '../../stores/registryStore.js'
import RuleDrawer from './RuleDrawer.jsx'

const DEPARTMENTS = ['Order Intake', 'Fulfillment', 'Shipping', 'Billing', 'Notifications', 'Analytics', 'Compliance']
const STATUSES    = ['active', 'paused', 'planned', 'deferred']
const RISK_LEVELS = ['low', 'medium', 'high', 'critical']

const MOCK_RULES = Array.from({ length: 24 }, (_, i) => {
  const dept = DEPARTMENTS[i % DEPARTMENTS.length]
  const prefix = dept.slice(0, 3).toUpperCase()
  return {
    rule_id:      `${prefix}-${String(i + 1).padStart(3, '0')}`,
    title:        `${dept} automation rule #${i + 1}`,
    department:   dept,
    status:       STATUSES[i % STATUSES.length],
    risk_level:   RISK_LEVELS[i % RISK_LEVELS.length],
    owner:        ['alice@co.com', 'bob@co.com', 'carol@co.com', 'system'][i % 4],
    last_changed: new Date(Date.now() - i * 3_600_000 * 7).toISOString(),
    verified:     i % 3 !== 0,
  }
})

const Ic = {
  search:  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5l3 3"/></svg>,
  x:       <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 3l6 6M9 3l-6 6"/></svg>,
  down:    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 4.5l3 3 3-3"/></svg>,
  check:   <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M2 6.5l2.5 2.5L10 3.5"/></svg>,
  sort:    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M5 2v6M3 6l2 2 2-2M3 4l2-2 2 2"/></svg>,
  refresh: <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M13 7a5 5 0 1 0-1.5 3.5M13 3v3h-3"/></svg>,
  plus:    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 3v10M3 8h10"/></svg>,
}

function timeAgo(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86_400_000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(new Date(iso))
}

const RISK_KIND = { critical: 'crit', high: 'high', medium: 'med', low: 'low' }
const STATUS_KIND = { active: 'active', paused: 'paused', planned: 'planned', deferred: 'deferred' }

function Pill({ kind, children }) {
  return (
    <span className={`pill${kind ? ` ${kind}` : ''}`}>
      {kind && <span className="dot" />}
      {children}
    </span>
  )
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
  const displayValue = value || 'All'
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <div className="select" onClick={() => setOpen(o => !o)}>
        <span className="lbl">{label}:</span>
        <span>{displayValue.charAt(0).toUpperCase() + displayValue.slice(1)}</span>
        <span className="caret">{Ic.down}</span>
      </div>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', right: 0,
          background: 'var(--vellum)', border: '1px solid var(--rule)',
          minWidth: 170, zIndex: 20, padding: 4,
          borderRadius: 'var(--radius)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
        }}>
          {options.map(o => {
            const label = o === '' ? 'All' : o.charAt(0).toUpperCase() + o.slice(1)
            return (
              <div key={o || 'all'} onClick={() => { onChange(o); setOpen(false) }}
                style={{
                  padding: '6px 10px', fontSize: 12.5, cursor: 'pointer',
                  borderRadius: 4,
                  background: o === value ? 'var(--paper-2)' : 'transparent',
                  color: 'var(--ink-2)',
                }}>
                {label}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function RegistryPage() {
  const {
    rules, totalCount, filters, loading, selectedRule,
    fetchRules, selectRule, updateFilter, clearFilters, setSort,
  } = useRegistryStore()

  const [displayRules, setDisplayRules] = useState([])
  const [searchParams] = useSearchParams()

  // Apply URL-derived filters once on mount (verified=false, status=active, risk_level=critical, etc)
  useEffect(() => {
    const upd = {}
    const v = searchParams.get('verified')
    if (v === 'false') upd.verified = false
    if (v === 'true')  upd.verified = true
    const status = searchParams.get('status')
    if (status) upd.status = status
    const risk = searchParams.get('risk_level')
    if (risk) upd.risk_level = risk
    if (Object.keys(upd).length) updateFilter(upd)
    fetchRules().catch(() => setDisplayRules(MOCK_RULES))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (rules.length > 0) setDisplayRules(rules)
    else if (!loading)     setDisplayRules(MOCK_RULES)
  }, [rules, loading])

  const total = totalCount || displayRules.length
  const verifLabel = filters.verified === true ? 'Verified only'
    : filters.verified === false ? 'Unverified only' : 'All'

  return (
    <>
      <header className="page-head">
        <div>
          <div className="folio">§ II · Registry</div>
          <h1>Registry <em>of rules</em></h1>
          <div className="lede">
            The definitive list of every automation rule. Search, filter, and inspect —
            every change is logged in the audit ledger.
          </div>
        </div>
        <div className="head-actions">
          <button className="btn sm" onClick={() => fetchRules()} disabled={loading}>
            {Ic.refresh} Refresh
          </button>
          <button className="btn sm primary">
            {Ic.plus} New rule
          </button>
        </div>
      </header>

      <div className="l-row mb16" style={{ flexWrap: 'wrap', gap: 10 }}>
        <div className="input" style={{ flex: 1, minWidth: 280, maxWidth: 440 }}>
          <span className="pre">{Ic.search}</span>
          <input
            placeholder="Search rules by id or title…"
            value={filters.search ?? ''}
            onChange={e => updateFilter({ search: e.target.value })}
          />
          {filters.search && (
            <button onClick={() => updateFilter({ search: '' })} style={{ color: 'var(--ink-4)' }}>
              {Ic.x}
            </button>
          )}
        </div>
        <div className="right l-row gap8" style={{ flexWrap: 'wrap' }}>
          <Dd label="Dept"   value={filters.department ?? ''} onChange={v => updateFilter({ department: v })} options={['', ...DEPARTMENTS]} />
          <Dd label="Status" value={filters.status ?? ''}     onChange={v => updateFilter({ status: v })}     options={['', ...STATUSES]} />
          <Dd label="Risk"   value={filters.risk_level ?? ''} onChange={v => updateFilter({ risk_level: v })} options={['', ...RISK_LEVELS]} />
          <div
            className="select"
            onClick={() => updateFilter({
              verified: filters.verified === true ? false : filters.verified === false ? null : true,
            })}
            title="Click to cycle: all → verified → unverified"
          >
            <span style={{
              display: 'inline-block', width: 12, height: 12,
              border: '1.3px solid var(--ink-3)',
              background: filters.verified === true ? 'var(--ink)'
                : filters.verified === false ? 'var(--paper-3)' : 'transparent',
              borderRadius: 3,
            }} />
            {verifLabel}
          </div>
          {(filters.search || filters.department || filters.status || filters.risk_level || filters.verified !== null) && (
            <button className="btn sm ghost" onClick={clearFilters}>
              {Ic.x} Clear
            </button>
          )}
        </div>
      </div>

      <div className="table-wrap">
        <table className="l-table">
          <thead>
            <tr>
              <th style={{ width: 120, cursor: 'pointer' }} onClick={() => setSort?.('rule_id')}>
                Rule <span className="sort">{Ic.sort}</span>
              </th>
              <th onClick={() => setSort?.('title')} style={{ cursor: 'pointer' }}>
                Title <span className="sort">{Ic.sort}</span>
              </th>
              <th style={{ width: 130 }}>Department</th>
              <th style={{ width: 100 }}>Status</th>
              <th style={{ width: 100 }}>Risk</th>
              <th style={{ width: 170 }}>Owner</th>
              <th style={{ width: 110 }}>Changed</th>
              <th style={{ width: 90 }}>Verified</th>
            </tr>
          </thead>
          <tbody>
            {loading && displayRules.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 40, color: 'var(--ink-4)' }}>
                  Loading rules…
                </td>
              </tr>
            ) : displayRules.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-4)' }}>
                  <div style={{ marginBottom: 8, color: 'var(--ink-3)' }}>No rules match your filters.</div>
                  <button className="btn sm" onClick={clearFilters}>Clear filters</button>
                </td>
              </tr>
            ) : displayRules.map(r => {
              const critUnverified = r.risk_level === 'critical' && !r.verified
              const highUnverified = r.risk_level === 'high'     && !r.verified
              const rowClass = selectedRule?.rule_id === r.rule_id ? 'selected'
                : critUnverified ? 'focus-row'
                : highUnverified ? 'warn-row'
                : ''
              return (
                <tr key={r.rule_id} className={rowClass} onClick={() => selectRule(r.rule_id)}>
                  <td className="id-cell">
                    {r.rule_id}
                    {!r.verified && <span className="flag">●</span>}
                  </td>
                  <td>{r.title}</td>
                  <td className="dim">{r.department ?? '—'}</td>
                  <td>
                    <Pill kind={STATUS_KIND[r.status]}>
                      {r.status ? r.status.charAt(0).toUpperCase() + r.status.slice(1) : '—'}
                    </Pill>
                  </td>
                  <td>
                    <Pill kind={RISK_KIND[r.risk_level]}>
                      {r.risk_level ? r.risk_level.charAt(0).toUpperCase() + r.risk_level.slice(1) : '—'}
                    </Pill>
                  </td>
                  <td className="dim mono" style={{ fontSize: 12 }}>{r.owner ?? '—'}</td>
                  <td className="dim">{timeAgo(r.last_changed)}</td>
                  <td>
                    {r.verified
                      ? <span style={{ color: 'var(--ok)', display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}>{Ic.check} Signed</span>
                      : <span className="dim" style={{ fontSize: 12 }}>pending</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {total > (filters.page_size ?? 50) && (
        <div className="l-row mt16" style={{ justifyContent: 'space-between' }}>
          <div className="dim" style={{ fontSize: 12 }}>
            Showing {displayRules.length} of {total.toLocaleString()}
          </div>
          <div className="l-row gap8">
            <button
              className="btn sm"
              onClick={() => updateFilter({ page: (filters.page ?? 1) - 1 })}
              disabled={(filters.page ?? 1) <= 1}
            >‹</button>
            <span className="mono dim" style={{ fontSize: 12 }}>
              {filters.page ?? 1} / {Math.max(1, Math.ceil(total / (filters.page_size ?? 50)))}
            </span>
            <button
              className="btn sm"
              onClick={() => updateFilter({ page: (filters.page ?? 1) + 1 })}
              disabled={(filters.page ?? 1) * (filters.page_size ?? 50) >= total}
            >›</button>
          </div>
        </div>
      )}

      <RuleDrawer />
    </>
  )
}
