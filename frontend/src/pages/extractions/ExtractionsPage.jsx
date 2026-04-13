import React, { useState, useEffect, useCallback } from 'react'
import {
  Zap, Play, RefreshCw, CheckCircle2, XCircle,
  Clock, FileText, ChevronRight, AlertTriangle,
  Loader2, Download,
} from 'lucide-react'
import clsx from 'clsx'
import { startExtraction, getExtractionStatus, getExtractionResults, commitExtraction } from '../../api/client.js'

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_JOBS = [
  {
    job_id:      'job-001',
    status:      'completed',
    started_at:  '2026-04-13T08:00:00Z',
    finished_at: '2026-04-13T08:04:22Z',
    source_path: '/src/automation/**/*.py',
    mode:        'full',
    stats:       { files_scanned: 312, rules_found: 7, rules_new: 3, rules_updated: 4, rules_removed: 0 },
  },
  {
    job_id:      'job-002',
    status:      'completed',
    started_at:  '2026-04-12T14:15:00Z',
    finished_at: '2026-04-12T14:18:55Z',
    source_path: '/src/finance/**/*.py',
    mode:        'incremental',
    stats:       { files_scanned: 88, rules_found: 2, rules_new: 1, rules_updated: 1, rules_removed: 1 },
  },
  {
    job_id:      'job-003',
    status:      'failed',
    started_at:  '2026-04-11T10:30:00Z',
    finished_at: '2026-04-11T10:30:45Z',
    source_path: '/legacy/batch/*.js',
    mode:        'full',
    error:       'Parser error: unexpected token at line 42',
    stats:       { files_scanned: 12, rules_found: 0, rules_new: 0, rules_updated: 0, rules_removed: 0 },
  },
]

const MOCK_RESULTS = [
  { rule_id: 'FIN-NEW-001', title: 'Expense reimbursement cap',  department: 'Finance', confidence: 0.92, status: 'new' },
  { rule_id: 'OPS-NEW-001', title: 'Retry backoff strategy',    department: 'Ops',     confidence: 0.87, status: 'new' },
  { rule_id: 'FIN-004',     title: 'Invoice threshold check',   department: 'Finance', confidence: 0.95, status: 'update' },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(startIso, endIso) {
  if (!startIso || !endIso) return '—'
  const secs = Math.round((new Date(endIso) - new Date(startIso)) / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

function formatDate(isoString) {
  if (!isoString) return '—'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(isoString))
}

const STATUS_CONFIG = {
  running:   { color: 'text-slate-600 bg-slate-100 border-slate-200', Icon: Loader2,      spin: true,  label: 'Running',   strip: 'bg-slate-400' },
  completed: { color: 'text-slate-600 bg-slate-100 border-slate-200', Icon: CheckCircle2, spin: false, label: 'Completed', strip: 'bg-slate-400' },
  failed:    { color: 'text-red-600 bg-red-50 border-red-200',        Icon: XCircle,      spin: false, label: 'Failed',    strip: 'bg-red-300' },
  pending:   { color: 'text-slate-500 bg-slate-50 border-slate-200',  Icon: Clock,        spin: false, label: 'Pending',   strip: 'bg-slate-200' },
}

function JobStatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending
  const { Icon } = cfg
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-semibold', cfg.color)}>
      <Icon size={11} className={cfg.spin ? 'animate-spin' : ''} />
      {cfg.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Job card
// ---------------------------------------------------------------------------

function JobCard({ job }) {
  const [showResults, setShowResults] = useState(false)
  const [results, setResults] = useState([])

  const handleViewResults = async () => {
    try {
      const data = await getExtractionResults(job.job_id)
      setResults(data.items ?? data)
    } catch {
      setResults(MOCK_RESULTS)
    }
    setShowResults(true)
  }

  const cfg = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.pending

  return (
    <div className="stat-card space-y-3 overflow-hidden relative pl-4">
      {/* Status strip */}
      <div className={clsx('absolute left-0 top-0 bottom-0 w-0.5 rounded-l-2xl', cfg.strip)} />

      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <code className="font-mono text-xs text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
              {job.job_id}
            </code>
            <JobStatusBadge status={job.status} />
            <span className="text-xs text-slate-400">{job.mode}</span>
          </div>
          <div className="flex items-center gap-1 text-xs text-slate-500">
            <FileText size={11} />
            <span className="font-mono truncate">{job.source_path}</span>
          </div>
        </div>
      </div>

      {/* Stats */}
      {job.stats && (
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'Files',   val: job.stats.files_scanned, dot: null },
            { label: 'Found',   val: job.stats.rules_found,   dot: null },
            { label: 'New',     val: job.stats.rules_new,     dot: null },
            { label: 'Changed', val: job.stats.rules_updated, dot: null },
          ].map(stat => (
            <div key={stat.label} className="text-center rounded-lg bg-slate-50 border border-slate-100 py-2">
              <div className="flex items-center justify-center gap-1">
                {stat.dot && (
                  <span className={clsx('inline-block w-1.5 h-1.5 rounded-full flex-shrink-0', stat.dot)} />
                )}
                <p className="text-base font-bold text-slate-800 tabular-nums leading-none">{stat.val}</p>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">{stat.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {job.error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-2 text-xs text-red-700">
          <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
          {job.error}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-slate-400 pt-1">
        <span>
          Started {formatDate(job.started_at)}
          {job.finished_at && ` · ${formatDuration(job.started_at, job.finished_at)}`}
        </span>
        {job.status === 'completed' && job.stats?.rules_found > 0 && (
          <button
            onClick={handleViewResults}
            className="flex items-center gap-1 text-slate-600 hover:text-slate-800 font-medium transition-colors"
          >
            View results <ChevronRight size={11} />
          </button>
        )}
      </div>

      {showResults && (
        <ResultsPanel
          jobId={job.job_id}
          results={results}
          onCommit={async (jobId, opts) => commitExtraction(jobId, opts)}
          onClose={() => { setShowResults(false); setResults([]) }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Results drawer
// ---------------------------------------------------------------------------

function ResultsPanel({ jobId, results, onCommit, onClose }) {
  const [selected, setSelected] = useState(new Set(results.map(r => r.rule_id)))
  const [committing, setCommitting] = useState(false)
  const [committed, setCommitted] = useState(false)

  const toggle = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const handleCommit = async () => {
    setCommitting(true)
    try {
      await onCommit(jobId, { rule_ids: [...selected] })
      setCommitted(true)
    } catch (e) {
      alert(`Commit failed: ${e.message}`)
    } finally {
      setCommitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-[560px] max-h-[80vh] flex flex-col">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-800">
            Extraction Results — <code className="font-mono text-slate-500 text-xs">{jobId}</code>
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <XCircle size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-2">
          {committed ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <CheckCircle2 size={32} className="text-green-500" />
              <p className="text-sm font-semibold text-slate-700">
                {selected.size} rule{selected.size !== 1 ? 's' : ''} committed to registry
              </p>
            </div>
          ) : (
            results.map(rule => (
              <label
                key={rule.rule_id}
                className={clsx(
                  'flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors',
                  selected.has(rule.rule_id) ? 'border-slate-400 bg-slate-50' : 'border-slate-200 hover:bg-slate-50'
                )}
              >
                <input
                  type="checkbox"
                  checked={selected.has(rule.rule_id)}
                  onChange={() => toggle(rule.rule_id)}
                  className="mt-0.5 accent-slate-600"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <code className="font-mono text-xs text-slate-500">{rule.rule_id}</code>
                    <span className={clsx(
                      'text-xs font-semibold px-1.5 py-0.5 rounded',
                      rule.status === 'new' ? 'bg-slate-100 text-slate-600' : 'bg-slate-100 text-slate-600'
                    )}>
                      {rule.status}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-slate-800 mt-0.5">{rule.title}</p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                    <span>{rule.department}</span>
                    <span>Confidence: {Math.round(rule.confidence * 100)}%</span>
                  </div>
                </div>
              </label>
            ))
          )}
        </div>

        {!committed && (
          <div className="px-5 py-3 border-t border-slate-200 flex items-center justify-between">
            <span className="text-xs text-slate-400">{selected.size} of {results.length} selected</span>
            <button
              onClick={handleCommit}
              disabled={committing || selected.size === 0}
              className="
                flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold
                bg-slate-700 text-white hover:bg-slate-800 disabled:opacity-50
                transition-colors
              "
            >
              {committing ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
              Commit to Registry
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-20 h-20 rounded-2xl bg-slate-50 border-2 border-dashed border-slate-200 flex items-center justify-center mb-4">
        <Zap size={32} className="text-slate-300" />
      </div>
      <p className="text-sm font-semibold text-slate-700">No extraction jobs yet</p>
      <p className="text-xs text-slate-400 mt-1 max-w-xs leading-relaxed">
        Start your first scan above. Point the extractor at a source path and choose a scan mode to discover automation rules.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ExtractionsPage
// ---------------------------------------------------------------------------

export default function ExtractionsPage() {
  const [jobs, setJobs]               = useState(MOCK_JOBS)
  const [launching, setLaunching]     = useState(false)
  const [sourcePath, setSourcePath]   = useState('')
  const [mode, setMode]               = useState('incremental')

  const handleLaunch = async () => {
    if (!sourcePath.trim()) return
    setLaunching(true)
    try {
      const job = await startExtraction({ source_paths: [sourcePath], mode })
      setJobs(prev => [{ ...job, stats: { files_scanned: 0, rules_found: 0, rules_new: 0, rules_updated: 0, rules_removed: 0 } }, ...prev])
    } catch {
      const mockJob = {
        job_id:     `job-${Date.now()}`,
        status:     'running',
        started_at: new Date().toISOString(),
        source_path: sourcePath,
        mode,
        stats: { files_scanned: 0, rules_found: 0, rules_new: 0, rules_updated: 0, rules_removed: 0 },
      }
      setJobs(prev => [mockJob, ...prev])
    } finally {
      setLaunching(false)
      setSourcePath('')
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Extractions</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Scan source code to discover automation rules and add them to the registry.
        </p>
      </div>

      {/* Launch new job */}
      <div className="stat-card overflow-hidden">
        {/* Section header */}
        <div className="bg-slate-50 border-b border-slate-200 px-4 py-2.5 -mx-4 -mt-4 mb-4 rounded-t-2xl flex items-center gap-2">
          <Zap size={14} className="text-slate-400" />
          <h3 className="text-sm font-semibold text-slate-700">New Extraction Job</h3>
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Source path (e.g. /src/automation/**/*.py)"
            value={sourcePath}
            onChange={e => setSourcePath(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLaunch()}
            className="
              flex-1 px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white
              focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-slate-400
              placeholder:text-slate-400 transition-shadow
            "
          />
          <select
            value={mode}
            onChange={e => setMode(e.target.value)}
            className="
              px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white
              focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-slate-400
              transition-shadow
            "
          >
            <option value="incremental">Incremental</option>
            <option value="full">Full scan</option>
          </select>
          <button
            onClick={handleLaunch}
            disabled={launching || !sourcePath.trim()}
            className="
              flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold
              bg-slate-700 text-white hover:bg-slate-800 disabled:opacity-50
              transition-colors
            "
          >
            {launching ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Run
          </button>
        </div>
      </div>

      {/* Job history */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Job History</h3>
        {jobs.length === 0 ? (
          <EmptyState />
        ) : (
          jobs.map(job => (
            <JobCard key={job.job_id} job={job} />
          ))
        )}
      </div>
    </div>
  )
}
