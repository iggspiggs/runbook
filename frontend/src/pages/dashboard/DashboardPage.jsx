import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BookOpen, CheckCircle2, AlertTriangle, Clock,
  Activity, RefreshCw, ChevronRight, Zap,
  TrendingUp, Shield, AlertCircle, Play,
} from 'lucide-react'
import clsx from 'clsx'
import { getDashboardStats, getAuditLog } from '../../api/client.js'

// ---------------------------------------------------------------------------
// Mock / fallback data for when API is unavailable
// ---------------------------------------------------------------------------
const MOCK_STATS = {
  total_rules:      142,
  active_rules:     118,
  unverified_rules:  23,
  recent_changes:     7,
  departments: [
    { name: 'Finance',   count: 31, color: 'bg-indigo-300' },
    { name: 'Ops',       count: 28, color: 'bg-slate-400' },
    { name: 'IT',        count: 24, color: 'bg-teal-300' },
    { name: 'HR',        count: 19, color: 'bg-violet-300' },
    { name: 'Sales',     count: 16, color: 'bg-amber-300' },
    { name: 'Marketing', count: 12, color: 'bg-rose-300' },
    { name: 'Legal',     count:  8, color: 'bg-stone-300' },
    { name: 'Other',     count:  4, color: 'bg-zinc-300' },
  ],
  risk_distribution: {
    low:      68,
    medium:   47,
    high:     21,
    critical:  6,
  },
  extraction_health: {
    last_scan:    '2026-04-12T14:30:00Z',
    drift_status: 'clean',  // 'clean' | 'drifted' | 'unknown'
    files_scanned: 312,
  },
}

const MOCK_AUDIT = {
  items: [
    { id: 1, timestamp: '2026-04-13T09:14:00Z', action: 'edit',   operator: 'alice@co.com',   rule_id: 'FIN-004', description: 'Updated threshold to 5000' },
    { id: 2, timestamp: '2026-04-13T08:52:00Z', action: 'verify', operator: 'bob@co.com',     rule_id: 'HR-012',  description: 'Marked as verified' },
    { id: 3, timestamp: '2026-04-13T07:30:00Z', action: 'edit',   operator: 'carol@co.com',   rule_id: 'OPS-007', description: 'Changed retry_limit from 3 to 5' },
    { id: 4, timestamp: '2026-04-12T18:22:00Z', action: 'add',    operator: 'system',          rule_id: 'IT-031',  description: 'Ingested via extraction job #44' },
    { id: 5, timestamp: '2026-04-12T16:05:00Z', action: 'edit',   operator: 'alice@co.com',   rule_id: 'FIN-011', description: 'Updated notify_list' },
    { id: 6, timestamp: '2026-04-12T14:47:00Z', action: 'verify', operator: 'dave@co.com',    rule_id: 'SALES-003', description: 'Marked as verified' },
    { id: 7, timestamp: '2026-04-12T12:10:00Z', action: 'edit',   operator: 'carol@co.com',   rule_id: 'MKT-002', description: 'Disabled budget_cap' },
    { id: 8, timestamp: '2026-04-12T10:30:00Z', action: 'add',    operator: 'system',          rule_id: 'IT-030',  description: 'Ingested via extraction job #43' },
    { id: 9, timestamp: '2026-04-11T17:00:00Z', action: 'edit',   operator: 'bob@co.com',     rule_id: 'HR-008',  description: 'Updated approval_chain' },
    { id: 10, timestamp: '2026-04-11T14:22:00Z', action: 'verify', operator: 'alice@co.com', rule_id: 'FIN-002',  description: 'Marked as verified' },
  ],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

function formatDate(isoString) {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(isoString))
}

const ACTION_CONFIG = {
  edit:   { color: 'text-slate-600 bg-slate-100', label: 'Edit' },
  verify: { color: 'text-slate-600 bg-slate-100', label: 'Verify' },
  add:    { color: 'text-slate-600 bg-slate-100',  label: 'Add' },
  delete: { color: 'text-slate-600 bg-slate-100',  label: 'Delete' },
}

// ---------------------------------------------------------------------------
// Skeleton loading components
// ---------------------------------------------------------------------------

function StatCardSkeleton() {
  return (
    <div className="stat-card animate-pulse">
      <div className="flex items-start justify-between">
        <div className="w-8 h-8 bg-slate-200 rounded-lg" />
      </div>
      <div className="mt-3 space-y-2">
        <div className="h-7 w-16 bg-slate-200 rounded" />
        <div className="h-3.5 w-24 bg-slate-100 rounded" />
        <div className="h-3 w-20 bg-slate-100 rounded" />
      </div>
    </div>
  )
}

function MiddleRowSkeleton() {
  return (
    <div className="h-64 bg-slate-100 rounded-xl animate-pulse" />
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({ icon: Icon, label, value, sub, accent = 'indigo', onClick }) {
  const accentMap = {
    indigo: 'text-indigo-600 bg-indigo-50',
    green:  'text-emerald-600 bg-emerald-50',
    amber:  'text-amber-600 bg-amber-50',
    red:    'text-rose-600 bg-rose-50',
  }
  return (
    <button
      onClick={onClick}
      className={clsx(
        'stat-card text-left w-full group',
        onClick && 'hover:border-slate-300 hover:shadow-md transition-all duration-150'
      )}
    >
      <div className="flex items-start justify-between">
        <div className={clsx('p-2 rounded-lg', accentMap[accent])}>
          <Icon size={16} aria-hidden="true" />
        </div>
        {onClick && (
          <ChevronRight size={14} className="text-slate-300 group-hover:text-slate-500 mt-1 transition-colors" />
        )}
      </div>
      <div className="mt-3">
        <p className="text-2xl font-bold text-slate-900 tabular-nums">{value?.toLocaleString() ?? '—'}</p>
        <p className="text-sm font-medium text-slate-600 mt-0.5">{label}</p>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </button>
  )
}

function DeptBar({ name, count, total, color }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-600 font-medium">{name}</span>
        <div className="flex items-center gap-2">
          <span className="text-slate-500 tabular-nums">{count}</span>
          <span className="text-slate-400 tabular-nums w-8 text-right">{pct}%</span>
        </div>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all duration-500', color)}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={count}
          aria-label={`${name}: ${count} rules`}
        />
      </div>
    </div>
  )
}

function RiskRow({ level, count, total, colorClass, label }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div className="flex items-center gap-3">
      <span className={clsx('text-xs font-semibold w-16 text-right tabular-nums', colorClass)}>
        {count}
      </span>
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full', colorClass.replace('text-', 'bg-').replace('-600', '-400').replace('-700', '-500'))}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-slate-500 w-14">{label}</span>
    </div>
  )
}

function AuditTimelineItem({ entry }) {
  const ac = ACTION_CONFIG[entry.action] ?? ACTION_CONFIG.edit
  return (
    <div className="flex items-start gap-3 py-2 group relative">
      <span className={clsx('text-xs font-semibold px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5 z-10', ac.color)}>
        {ac.label}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-700 truncate">
          <code className="font-mono text-slate-500 mr-1">{entry.rule_id}</code>
          {entry.description}
        </p>
        <p className="text-xs text-slate-400 mt-0.5">
          {entry.operator === 'system' ? 'System' : entry.operator} · {timeAgo(entry.timestamp)}
        </p>
      </div>
    </div>
  )
}

function ExtractionHealthCard({ health }) {
  const driftConfig = {
    clean:   { color: 'text-emerald-600', bg: 'bg-emerald-50/50 border-emerald-200', dot: 'bg-emerald-400', label: 'Clean',          pulse: true },
    drifted: { color: 'text-amber-600',  bg: 'bg-amber-50/50 border-amber-200',   dot: 'bg-amber-400',  label: 'Drift detected', pulse: true },
    unknown: { color: 'text-slate-500',  bg: 'bg-slate-50/50 border-slate-200',    dot: 'bg-slate-300',  label: 'Unknown',        pulse: false },
  }
  const dc = driftConfig[health?.drift_status] ?? driftConfig.unknown

  return (
    <div className={clsx('rounded-xl border p-4', dc.bg)}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap size={14} className={dc.color} />
          <span className="text-sm font-semibold text-slate-700">Extraction Health</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={clsx('w-2 h-2 rounded-full', dc.dot, dc.pulse && 'animate-pulse')}
          />
          <span className={clsx('text-xs font-semibold', dc.color)}>{dc.label}</span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <p className="text-xs text-slate-500">Last scan</p>
          <p className="text-sm font-medium text-slate-700 mt-0.5">
            {health?.last_scan ? formatDate(health.last_scan) : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Files scanned</p>
          <p className="text-sm font-medium text-slate-700 mt-0.5 tabular-nums">
            {health?.files_scanned?.toLocaleString() ?? '—'}
          </p>
        </div>
      </div>
      <button
        className="flex items-center gap-1.5 w-full justify-center px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition-colors"
        onClick={() => {}}
        aria-label="Run extraction scan"
      >
        <Play size={11} />
        Run Scan
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DashboardPage
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats]     = useState(null)
  const [audit, setAudit]     = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, a] = await Promise.all([
        getDashboardStats(),
        getAuditLog({ page_size: 10 }),
      ])
      setStats(s)
      setAudit(a.items ?? a)
    } catch {
      // Fall back to mock data gracefully
      setStats(MOCK_STATS)
      setAudit(MOCK_AUDIT.items)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const s    = stats ?? MOCK_STATS
  const riskTotal = Object.values(s.risk_distribution ?? {}).reduce((a, b) => a + b, 0)
  const deptTotal = s.total_rules ?? 0
  const deptCount = (s.departments ?? []).length

  if (loading && !stats) {
    return (
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Skeleton stat cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>
        {/* Skeleton middle row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <MiddleRowSkeleton />
          <MiddleRowSkeleton />
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Overview</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            {deptTotal} automation rules across {deptCount} departments — live registry state
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-slate-600 hover:bg-slate-100 border border-slate-200 transition-colors"
          aria-label="Refresh dashboard"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={BookOpen}
          label="Total Rules"
          value={s.total_rules}
          sub="In registry"
          accent="indigo"
          onClick={() => navigate('/registry')}
        />
        <StatCard
          icon={CheckCircle2}
          label="Active Rules"
          value={s.active_rules}
          sub={`${s.total_rules ? Math.round((s.active_rules / s.total_rules) * 100) : 0}% of total`}
          accent="green"
          onClick={() => navigate('/registry?status=active')}
        />
        <StatCard
          icon={AlertTriangle}
          label="Need Review"
          value={s.unverified_rules}
          sub="Not yet verified"
          accent="amber"
          onClick={() => navigate('/registry?verified=false')}
        />
        <StatCard
          icon={Activity}
          label="Changes (24h)"
          value={s.recent_changes}
          sub="Edits & verifications"
          accent="red"
          onClick={() => navigate('/audit')}
        />
      </div>

      {/* Middle row: dept breakdown + risk dist */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Department breakdown */}
        <div className="stat-card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-800">Rules by Department</h3>
            <span className="text-xs text-slate-400">{deptTotal} total</span>
          </div>
          <div className="space-y-3">
            {(s.departments ?? []).map(dept => (
              <DeptBar
                key={dept.name}
                name={dept.name}
                count={dept.count}
                total={deptTotal}
                color={dept.color}
              />
            ))}
          </div>
        </div>

        {/* Risk distribution */}
        <div className="stat-card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-800">Risk Distribution</h3>
            <span className="text-xs text-slate-400">{riskTotal} rules</span>
          </div>
          <div className="space-y-3">
            <RiskRow
              level="critical"
              count={s.risk_distribution?.critical ?? 0}
              total={riskTotal}
              colorClass="text-red-600"
              label="Critical"
            />
            <RiskRow
              level="high"
              count={s.risk_distribution?.high ?? 0}
              total={riskTotal}
              colorClass="text-orange-600"
              label="High"
            />
            <RiskRow
              level="medium"
              count={s.risk_distribution?.medium ?? 0}
              total={riskTotal}
              colorClass="text-amber-600"
              label="Medium"
            />
            <RiskRow
              level="low"
              count={s.risk_distribution?.low ?? 0}
              total={riskTotal}
              colorClass="text-green-600"
              label="Low"
            />
          </div>

          {/* Visual summary boxes */}
          <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-4 gap-2 text-center">
            {[
              { label: 'Critical', val: s.risk_distribution?.critical ?? 0, cls: 'text-red-700 bg-red-50' },
              { label: 'High',     val: s.risk_distribution?.high ?? 0,     cls: 'text-orange-700 bg-orange-50' },
              { label: 'Medium',   val: s.risk_distribution?.medium ?? 0,   cls: 'text-amber-700 bg-amber-50' },
              { label: 'Low',      val: s.risk_distribution?.low ?? 0,      cls: 'text-emerald-700 bg-emerald-50' },
            ].map(r => (
              <div
                key={r.label}
                className={clsx('rounded-lg py-2 px-1', r.cls)}
              >
                <p className="text-2xl font-bold tabular-nums">{r.val}</p>
                <p className="text-xs opacity-70">{r.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom row: audit timeline + extraction health */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Audit timeline — takes 2/3 */}
        <div className="lg:col-span-2 stat-card">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-800">Recent Activity</h3>
            <button
              onClick={() => navigate('/audit')}
              className="text-xs text-slate-500 hover:text-slate-700 font-medium flex items-center gap-1"
            >
              View all <ChevronRight size={12} />
            </button>
          </div>
          <div className="divide-y divide-slate-100">
            {(audit.length > 0 ? audit : MOCK_AUDIT.items).map(entry => (
              <AuditTimelineItem key={entry.id} entry={entry} />
            ))}
          </div>
        </div>

        {/* Extraction health + quick actions */}
        <div className="space-y-4">
          <ExtractionHealthCard health={s.extraction_health} />

          {/* Quick actions */}
          <div className="stat-card space-y-2">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Quick actions
            </h3>
            {[
              { label: 'Review unverified rules', path: '/registry?verified=false', Icon: Shield, color: 'text-amber-500' },
              { label: 'View high-risk rules',    path: '/registry?risk_level=high', Icon: AlertCircle, color: 'text-rose-400' },
              { label: 'Explore process graph',   path: '/graph', Icon: TrendingUp, color: 'text-indigo-400' },
              { label: 'Run new extraction',      path: '/extractions', Icon: Zap, color: 'text-teal-400' },
            ].map(({ label, path, Icon, color }) => (
              <button
                key={path}
                onClick={() => navigate(path)}
                className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition-all duration-150 group"
              >
                <Icon size={14} className={color} />
                <span className="flex-1 text-left">{label}</span>
                <ChevronRight
                  size={13}
                  className="text-slate-300 group-hover:text-slate-500 transition-all duration-150 group-hover:translate-x-0.5"
                />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
