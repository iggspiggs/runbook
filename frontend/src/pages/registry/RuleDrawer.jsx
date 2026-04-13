import React, { useEffect, useRef, useState } from 'react'
import {
  X, CheckCircle2, AlertTriangle,
  Zap, GitMerge, User, Clock, Shield,
  ChevronRight, Loader2, BarChart2,
} from 'lucide-react'
import clsx from 'clsx'
import RiskBadge from '../../components/common/RiskBadge.jsx'
import StatusBadge from '../../components/common/StatusBadge.jsx'
import EditableField from '../../components/common/EditableField.jsx'
import useRegistryStore from '../../stores/registryStore.js'
import { getRuleAudit } from '../../api/client.js'

// ---------------------------------------------------------------------------
// Department accent colors (neutralized — kept for API compat)
// ---------------------------------------------------------------------------

function deptColor(_dept) {
  return '#a8a29e'
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(isoString) {
  if (!isoString) return '—'
  const diff = Date.now() - new Date(isoString).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function formatDate(isoString) {
  if (!isoString) return '—'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(isoString))
}

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------
function Section({ title, icon: Icon, children, className }) {
  return (
    <div className={clsx('space-y-2', className)}>
      <div className="flex items-center gap-1.5">
        {Icon && <Icon size={12} className="text-slate-400 flex-shrink-0" />}
        <h4 className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest">
          {title}
        </h4>
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Confidence bar
// ---------------------------------------------------------------------------
function ConfidenceBar({ score }) {
  const pct   = Math.round((score ?? 0) * 100)
  const color = pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-500">Extraction confidence</span>
        <span className="font-semibold text-slate-700">{pct}%</span>
      </div>
      <div className="confidence-track">
        <div className={clsx('confidence-fill', color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Dependency chip
// ---------------------------------------------------------------------------
function DepChip({ ruleId, onSelect, variant = 'upstream' }) {
  return (
    <button
      onClick={() => onSelect(ruleId)}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-slate-200 bg-slate-100 text-slate-600 hover:bg-slate-200 text-xs font-mono transition-colors"
    >
      {ruleId}
      <ChevronRight size={10} />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Audit trail item
// ---------------------------------------------------------------------------
function AuditItem({ entry, isLast }) {
  const actionMeta = {
    edit:   { badge: 'bg-slate-100 text-slate-600', dot: 'bg-slate-300' },
    verify: { badge: 'bg-slate-100 text-slate-600', dot: 'bg-slate-300' },
    add:    { badge: 'bg-slate-100 text-slate-600', dot: 'bg-slate-300' },
  }
  const meta = actionMeta[entry.action] ?? actionMeta.edit

  return (
    <div className="flex items-start gap-3 py-1.5 text-xs">
      {/* Timeline dot + line */}
      <div className="flex flex-col items-center flex-shrink-0 pt-1">
        <span className={clsx('w-2 h-2 rounded-full flex-shrink-0', meta.dot)} />
        {!isLast && <span className="w-px flex-1 bg-slate-100 mt-1 min-h-[12px]" />}
      </div>
      {/* Content */}
      <div className="flex-1 min-w-0 pb-1">
        <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
          <span className={clsx(
            'px-1.5 py-0.5 rounded font-semibold uppercase tracking-wide text-[10px]',
            meta.badge
          )}>
            {entry.action}
          </span>
          <span className="text-slate-400">{timeAgo(entry.timestamp)}</span>
        </div>
        <p className="text-slate-700 leading-relaxed">{entry.description}</p>
        <p className="text-slate-400 mt-0.5">{entry.operator}</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RuleDrawer
// ---------------------------------------------------------------------------

/**
 * RuleDrawer — slide-out detail panel for a selected rule.
 * Reads rule + actions from registryStore.
 */
export default function RuleDrawer() {
  const { selectedRule: rule, drawerOpen, loadingRule, closeDrawer, saveEditable, markVerified, selectRule } =
    useRegistryStore()

  const drawerRef = useRef(null)
  const [auditTrail, setAuditTrail] = useState([])

  // Trap focus and handle ESC
  useEffect(() => {
    if (!drawerOpen) return
    const handleKey = (e) => {
      if (e.key === 'Escape') closeDrawer()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [drawerOpen, closeDrawer])

  // Load per-rule audit trail when a rule is selected
  useEffect(() => {
    if (!rule?.rule_id) {
      setAuditTrail([])
      return
    }
    getRuleAudit(rule.rule_id, { page_size: 5 })
      .then(data => setAuditTrail(data.items ?? data))
      .catch(() => setAuditTrail([]))
  }, [rule?.rule_id])

  if (!drawerOpen) return null

  const handleSaveEditable = async (key, value) => {
    if (!rule) return
    await saveEditable(rule.rule_id, { [key]: value })
  }

  const handleVerify = async () => {
    if (!rule) return
    await markVerified(rule.rule_id)
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="drawer-backdrop"
        onClick={closeDrawer}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label={rule ? `Rule detail: ${rule.title}` : 'Rule detail'}
        className="
          fixed top-0 right-0 h-full w-[520px] max-w-full
          bg-white border-l border-slate-200 shadow-drawer
          z-50 flex flex-col animate-slide-in-right
          overflow-hidden transition-transform duration-300
        "
      >

        {/* Header */}
        <div className="flex-shrink-0 px-5 py-4 border-b border-slate-200 bg-white">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              {loadingRule && !rule ? (
                <div className="flex items-center gap-2 text-slate-400">
                  <Loader2 size={14} className="animate-spin" />
                  <span className="text-sm">Loading…</span>
                </div>
              ) : (
                <>
                  <h2 className="text-base font-semibold text-slate-900 leading-tight">
                    {rule?.title ?? 'Untitled Rule'}
                  </h2>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <code
                      className="font-mono text-sm font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md"
                    >
                      {rule?.rule_id ?? '—'}
                    </code>
                    {rule?.status && <StatusBadge status={rule.status} size="sm" />}
                    {rule?.risk_level && <RiskBadge level={rule.risk_level} size="sm" />}
                    {rule?.verified && (
                      <span className="inline-flex items-center gap-1 text-xs text-slate-500 font-medium">
                        <CheckCircle2 size={12} /> Verified
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
            <button
              onClick={closeDrawer}
              className="flex-shrink-0 p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
              aria-label="Close drawer"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        {rule && (
          <div className="flex-1 overflow-y-auto scrollbar-thin px-5 py-4 space-y-5">

            {/* Unverified warning + action */}
            {!rule.verified && (
              <div className="rounded-xl bg-amber-50 border border-amber-200 p-3.5 space-y-2">
                <div className="flex items-start gap-2">
                  <AlertTriangle size={14} className="text-amber-600 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 space-y-1">
                    <p className="text-xs font-semibold text-amber-800">Not yet verified</p>
                    <p className="text-xs text-amber-700">
                      This rule was extracted automatically and has not been reviewed by a human operator.
                    </p>
                    {rule.confidence_score !== undefined && (
                      <ConfidenceBar score={rule.confidence_score} />
                    )}
                  </div>
                </div>
                <button
                  onClick={handleVerify}
                  className="
                    flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold
                    bg-amber-600 text-white hover:bg-amber-700 transition-colors
                  "
                >
                  <Shield size={12} />
                  Mark as Verified
                </button>
              </div>
            )}

            {/* Business justification */}
            {rule.why && (
              <Section title="Why this rule exists">
                <p className="text-sm text-slate-700 leading-relaxed">{rule.why}</p>
              </Section>
            )}

            {/* Trigger */}
            {rule.trigger && (
              <Section title="Trigger" icon={Zap}>
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-sm text-slate-700">
                  <span className="font-medium text-slate-500 text-xs uppercase tracking-wide block mb-1">
                    {rule.trigger.type ?? 'Event'}
                  </span>
                  {rule.trigger.description ?? rule.trigger.event ?? JSON.stringify(rule.trigger)}
                </div>
              </Section>
            )}

            {/* Conditions */}
            {rule.conditions?.length > 0 && (
              <Section title="Conditions" icon={GitMerge}>
                <div className="space-y-1.5">
                  {rule.conditions.map((cond, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      <span className="flex-shrink-0 w-4 h-4 rounded-full bg-slate-200 text-slate-600 text-[10px] font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-slate-700 leading-relaxed">
                        {typeof cond === 'string' ? cond : cond.description ?? JSON.stringify(cond)}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Actions */}
            {rule.actions?.length > 0 && (
              <Section title="Actions">
                <div className="space-y-1.5">
                  {rule.actions.map((action, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      <span className="flex-shrink-0 font-mono text-xs text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-slate-700 leading-relaxed">
                        {typeof action === 'string' ? action : action.description ?? JSON.stringify(action)}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Editable fields */}
            {rule.editable_fields?.length > 0 && (
              <div className="rounded-xl bg-white border border-slate-200 px-3.5 pt-3 pb-3.5 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <BarChart2 size={12} className="text-slate-400 flex-shrink-0" />
                    <h4 className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest">
                      Editable Fields
                    </h4>
                  </div>
                  <span className="text-[10px] font-medium text-slate-500 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded">
                    Operator editable
                  </span>
                </div>
                <div className="space-y-2">
                  {rule.editable_fields.map(field => (
                    <EditableField
                      key={field.key}
                      ruleId={rule.rule_id}
                      field={field}
                      onSave={handleSaveEditable}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Source location */}
            {rule.source_file && (
              <Section title="Source">
                <div className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 font-mono text-xs text-green-400 flex items-center justify-between group">
                  <span className="truncate">
                    {rule.source_file}
                    {rule.source_lines?.length > 0 && (
                      <span className="text-slate-500 ml-1">
                        :{rule.source_lines[0]}{rule.source_lines.length > 1 ? `–${rule.source_lines[rule.source_lines.length - 1]}` : ''}
                      </span>
                    )}
                  </span>
                </div>
              </Section>
            )}

            {/* Dependencies */}
            {(rule.upstream_rule_ids?.length > 0 || rule.downstream_rule_ids?.length > 0) && (
              <Section title="Dependencies">
                <div className="space-y-2">
                  {rule.upstream_rule_ids?.length > 0 && (
                    <div>
                      <p className="text-xs text-slate-500 mb-1.5">Upstream (depends on)</p>
                      <div className="flex flex-wrap gap-1.5">
                        {rule.upstream_rule_ids.map(id => (
                          <DepChip key={id} ruleId={id} onSelect={selectRule} variant="upstream" />
                        ))}
                      </div>
                    </div>
                  )}
                  {rule.downstream_rule_ids?.length > 0 && (
                    <div>
                      <p className="text-xs text-slate-500 mb-1.5">Downstream (feeds into)</p>
                      <div className="flex flex-wrap gap-1.5">
                        {rule.downstream_rule_ids.map(id => (
                          <DepChip key={id} ruleId={id} onSelect={selectRule} variant="downstream" />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </Section>
            )}

            {/* Metadata row */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              {rule.owner && (
                <div className="flex items-start gap-1.5">
                  <User size={12} className="text-slate-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-slate-500">Owner</p>
                    <p className="font-medium text-slate-700">{rule.owner}</p>
                  </div>
                </div>
              )}
              {rule.department && (
                <div className="flex items-start gap-1.5">
                  <BarChart2 size={12} className="text-slate-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-slate-500">Department</p>
                    <p className="font-medium text-slate-700">{rule.department}</p>
                  </div>
                </div>
              )}
              {rule.last_changed && (
                <div className="flex items-start gap-1.5">
                  <Clock size={12} className="text-slate-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-slate-500">Last changed</p>
                    <p className="font-medium text-slate-700">{formatDate(rule.last_changed)}</p>
                  </div>
                </div>
              )}
              {rule.verified_by && (
                <div className="flex items-start gap-1.5">
                  <Shield size={12} className="text-slate-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-slate-500">Verified by</p>
                    <p className="font-medium text-slate-700">{rule.verified_by}</p>
                    {rule.verified_at && (
                      <p className="text-slate-400 mt-0.5">{formatDate(rule.verified_at)}</p>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Inline audit trail */}
            <Section title="Audit Trail" icon={Clock}>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                {auditTrail.length === 0 ? (
                  <p className="text-xs text-slate-400 py-2">No audit entries yet.</p>
                ) : (
                  auditTrail.slice(0, 5).map((entry, i, arr) => (
                    <AuditItem key={i} entry={entry} isLast={i === arr.length - 1} />
                  ))
                )}
              </div>
            </Section>

          </div>
        )}

        {/* Footer */}
        <div className="flex-shrink-0 px-5 py-3 border-t border-slate-100 bg-slate-50 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            {rule?.rule_id}
          </span>
          <button
            onClick={closeDrawer}
            className="text-xs text-slate-500 hover:text-slate-700 transition-colors"
          >
            Close
          </button>
        </div>
      </aside>
    </>
  )
}
