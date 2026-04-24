import React, { useState, useEffect, useRef } from 'react'
import { startExtraction, getExtractionResults, commitExtraction } from '../../api/client.js'

const MOCK_JOBS = [
  {
    job_id: 'job-001', status: 'completed',
    started_at: '2026-04-23T08:00:00Z', finished_at: '2026-04-23T08:04:22Z',
    source_path: '/src/automation/**/*.py', mode: 'full',
    stats: { files_scanned: 312, rules_found: 7, rules_new: 3, rules_updated: 4, rules_removed: 0 },
  },
  {
    job_id: 'job-002', status: 'completed',
    started_at: '2026-04-22T14:15:00Z', finished_at: '2026-04-22T14:18:55Z',
    source_path: '/src/finance/**/*.py', mode: 'incremental',
    stats: { files_scanned: 88, rules_found: 2, rules_new: 1, rules_updated: 1, rules_removed: 1 },
  },
  {
    job_id: 'job-003', status: 'failed',
    started_at: '2026-04-21T10:30:00Z', finished_at: '2026-04-21T10:30:45Z',
    source_path: '/legacy/batch/*.js', mode: 'full',
    error: 'Parser error: unexpected token at line 42',
    stats: { files_scanned: 12, rules_found: 0, rules_new: 0, rules_updated: 0, rules_removed: 0 },
  },
]

const MOCK_RESULTS = [
  { rule_id: 'FIN-NEW-001', title: 'Expense reimbursement cap',  department: 'Finance',    confidence: 0.92, status: 'new' },
  { rule_id: 'OPS-NEW-001', title: 'Retry backoff strategy',     department: 'Operations', confidence: 0.87, status: 'new' },
  { rule_id: 'FIN-004',     title: 'Invoice threshold check',    department: 'Finance',    confidence: 0.95, status: 'update' },
]

const Ic = {
  search:  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5l3 3"/></svg>,
  play:    <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M3 2l7 4-7 4z"/></svg>,
  down:    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 4.5l3 3 3-3"/></svg>,
  arrow:   <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 6h8M7 3l3 3-3 3"/></svg>,
  x:       <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 3l6 6M9 3l-6 6"/></svg>,
  check:   <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M2 6.5l2.5 2.5L10 3.5"/></svg>,
}

function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(new Date(iso))
  } catch { return iso }
}
function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return '—'
  const secs = Math.round((new Date(endIso) - new Date(startIso)) / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
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
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <div className="select" onClick={() => setOpen(o => !o)}>
        <span className="lbl">{label}:</span>
        <span>{value}</span>
        <span className="caret">{Ic.down}</span>
      </div>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', right: 0,
          background: 'var(--vellum)', border: '1px solid var(--rule)',
          minWidth: 160, zIndex: 20, padding: 4, borderRadius: 'var(--radius)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
        }}>
          {options.map(o => (
            <div key={o} onClick={() => { onChange(o); setOpen(false) }}
              style={{
                padding: '6px 10px', fontSize: 12.5, cursor: 'pointer',
                borderRadius: 4,
                background: o === value ? 'var(--paper-2)' : 'transparent',
                color: 'var(--ink-2)',
              }}>
              {o}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ResultsDialog({ jobId, results, onClose }) {
  const [selected, setSelected] = useState(new Set(results.map(r => r.rule_id)))
  const [committing, setCommitting] = useState(false)
  const [committed, setCommitted] = useState(false)

  const toggle = id => {
    setSelected(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  const handleCommit = async () => {
    setCommitting(true)
    try {
      await commitExtraction(jobId, { rule_ids: [...selected] })
      setCommitted(true)
    } catch (e) {
      alert(`Commit failed: ${e.message}`)
    } finally {
      setCommitting(false)
    }
  }

  return (
    <div className="drawer-backdrop" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        background: 'var(--vellum)', border: '1px solid var(--rule)',
        borderRadius: 'var(--radius)',
        width: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 10px 40px rgba(0,0,0,0.15)',
      }}>
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--rule-soft)',
          display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        }}>
          <div className="card-title" style={{ fontSize: 16 }}>
            Extraction results <span className="mono dim" style={{ fontSize: 12 }}>· {jobId}</span>
          </div>
          <button className="btn ghost sm" onClick={onClose}>{Ic.x}</button>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: 14 }}>
          {committed ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <div style={{ color: 'var(--ok)', display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                {Ic.check} {selected.size} rule{selected.size !== 1 ? 's' : ''} committed to the registry
              </div>
            </div>
          ) : results.map(r => (
            <label key={r.rule_id} style={{
              display: 'flex', gap: 10, alignItems: 'flex-start',
              border: `1px solid ${selected.has(r.rule_id) ? 'var(--ink-4)' : 'var(--rule-soft)'}`,
              background: selected.has(r.rule_id) ? 'var(--paper-2)' : 'var(--vellum)',
              borderRadius: 'var(--radius)', padding: 12, marginBottom: 8, cursor: 'pointer',
            }}>
              <input
                type="checkbox"
                checked={selected.has(r.rule_id)}
                onChange={() => toggle(r.rule_id)}
                style={{ marginTop: 2 }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <code className="id-cell">{r.rule_id}</code>
                  <Pill kind={r.status === 'new' ? 'planned' : ''}>{r.status}</Pill>
                </div>
                <div style={{ fontWeight: 500, marginTop: 2, color: 'var(--ink)' }}>{r.title}</div>
                <div className="dim" style={{ fontSize: 12, marginTop: 3 }}>
                  {r.department} · confidence {Math.round((r.confidence ?? 0) * 100)}%
                </div>
              </div>
            </label>
          ))}
        </div>

        {!committed && (
          <div style={{
            padding: '12px 20px', borderTop: '1px solid var(--rule-soft)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div className="dim" style={{ fontSize: 12 }}>
              {selected.size} of {results.length} selected
            </div>
            <button
              className="btn primary"
              disabled={committing || selected.size === 0}
              onClick={handleCommit}
            >
              {committing ? 'Committing…' : 'Commit to registry'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function ExtractionsPage() {
  const [jobs, setJobs] = useState(MOCK_JOBS)
  const [launching, setLaunching] = useState(false)
  const [sourcePath, setSourcePath] = useState('')
  const [mode, setMode] = useState('Incremental')
  const [resultsFor, setResultsFor] = useState(null)
  const [results, setResults] = useState([])

  const handleLaunch = async () => {
    if (!sourcePath.trim()) return
    setLaunching(true)
    try {
      const job = await startExtraction({ source_paths: [sourcePath], mode: mode.toLowerCase() })
      setJobs(prev => [
        { ...job, stats: { files_scanned: 0, rules_found: 0, rules_new: 0, rules_updated: 0, rules_removed: 0 } },
        ...prev,
      ])
    } catch {
      setJobs(prev => [{
        job_id: `job-${Date.now()}`, status: 'running',
        started_at: new Date().toISOString(),
        source_path: sourcePath, mode: mode.toLowerCase(),
        stats: { files_scanned: 0, rules_found: 0, rules_new: 0, rules_updated: 0, rules_removed: 0 },
      }, ...prev])
    } finally {
      setLaunching(false)
      setSourcePath('')
    }
  }

  const handleViewResults = async (jobId) => {
    try {
      const data = await getExtractionResults(jobId)
      setResults(data.items ?? data)
    } catch {
      setResults(MOCK_RESULTS)
    }
    setResultsFor(jobId)
  }

  return (
    <>
      <header className="page-head">
        <div>
          <div className="folio">§ IV · Extractions</div>
          <h1>Extractions <em>from source</em></h1>
          <div className="lede">
            Scan source code to discover automations and enroll them in the registry.
          </div>
        </div>
        <div className="head-actions">
          <div className="dim" style={{ fontSize: 12.5 }}>
            {jobs.length} jobs · last 30 days
          </div>
        </div>
      </header>

      <div className="l-card mb24" style={{ padding: '16px 18px' }}>
        <div className="card-head">
          <div className="card-title" style={{ fontSize: 16 }}>New extraction job</div>
          <div className="dim" style={{ fontSize: 12 }}>
            tip: use <code className="mono" style={{ fontSize: 11 }}>**/*.py</code> glob syntax
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 170px 130px', gap: 8 }}>
          <div className="input">
            <span className="pre">{Ic.search}</span>
            <input
              placeholder="/src/automation/**/*.py"
              value={sourcePath}
              onChange={e => setSourcePath(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLaunch()}
            />
          </div>
          <Dd label="Mode" value={mode} onChange={setMode} options={['Incremental', 'Full', 'Dry run']} />
          <button
            className="btn primary"
            style={{ justifyContent: 'center' }}
            disabled={launching || !sourcePath.trim()}
            onClick={handleLaunch}
          >
            {Ic.play} {launching ? 'Starting…' : 'Run scan'}
          </button>
        </div>
      </div>

      <div className="section-head">
        <div className="t">Recent jobs</div>
        <div className="m">{jobs.length} shown</div>
      </div>

      {jobs.length === 0 ? (
        <div className="l-card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="dim">No extraction jobs yet — start your first scan above.</div>
        </div>
      ) : jobs.map(j => {
        const stats = j.stats ?? {}
        const pillKind = j.status === 'failed' ? 'crit'
          : j.status === 'running' ? 'planned' : 'active'
        return (
          <div key={j.job_id} className="job">
            <div>
              <div className="job-head">
                <span className="job-id">{j.job_id}</span>
                <Pill kind={pillKind}>
                  {j.status.charAt(0).toUpperCase() + j.status.slice(1)}
                </Pill>
                <span className="dim" style={{ fontSize: 12 }}>· {j.mode}</span>
              </div>
              <span className="job-path">{j.source_path}</span>
              <div className="job-meta">
                Started {formatDate(j.started_at)}
                {j.finished_at && ` · ran for ${formatDuration(j.started_at, j.finished_at)}`}
              </div>
              {j.error && (
                <div style={{
                  marginTop: 10, padding: '8px 12px',
                  background: 'color-mix(in srgb, var(--risk-crit) 10%, var(--vellum))',
                  border: '1px solid color-mix(in srgb, var(--risk-crit) 30%, var(--rule))',
                  borderRadius: 'var(--radius)', fontSize: 12.5,
                  color: 'var(--risk-crit)',
                }}>
                  {j.error}
                </div>
              )}
              <div className="l-row mt8 gap8">
                {j.status === 'completed' && stats.rules_found > 0 && (
                  <button className="btn sm" onClick={() => handleViewResults(j.job_id)}>
                    View results {Ic.arrow}
                  </button>
                )}
                <button className="btn sm ghost">Re-run</button>
              </div>
            </div>
            <div className="job-stats">
              <div className="s"><div className="n">{stats.files_scanned ?? 0}</div><div className="l">Files</div></div>
              <div className="s"><div className="n">{stats.rules_found ?? 0}</div><div className="l">Found</div></div>
              <div className="s">
                <div className="n" style={{ color: stats.rules_new ? 'var(--accent)' : 'inherit' }}>
                  {stats.rules_new ?? 0}
                </div>
                <div className="l">New</div>
              </div>
              <div className="s"><div className="n">{stats.rules_updated ?? 0}</div><div className="l">Changed</div></div>
            </div>
          </div>
        )
      })}

      {resultsFor && (
        <ResultsDialog
          jobId={resultsFor}
          results={results}
          onClose={() => { setResultsFor(null); setResults([]) }}
        />
      )}
    </>
  )
}
