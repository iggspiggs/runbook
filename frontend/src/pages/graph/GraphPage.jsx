import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Panel,
} from 'reactflow'
import dagre from '@dagrejs/dagre'
import {
  User, Bot, Zap, Globe, RefreshCw, X, LayoutGrid,
  ChevronDown, ChevronRight, ArrowDown, ArrowRight,
  GitBranch, Rows3,
} from 'lucide-react'
import clsx from 'clsx'
import 'reactflow/dist/style.css'
import { getGraph, getRules } from '../../api/client.js'
import RiskBadge, { RiskDot } from '../../components/common/RiskBadge.jsx'
import StatusBadge from '../../components/common/StatusBadge.jsx'

// ---------------------------------------------------------------------------
// View modes
// ---------------------------------------------------------------------------
const VIEW_DAG = 'dag'
const VIEW_PIPELINE = 'pipeline'

// ---------------------------------------------------------------------------
// Department color map — extended for Acme Logistics demo departments
// ---------------------------------------------------------------------------
const DEPT_COLORS = {
  'Order Intake':   { bg: '#f5f3ff', border: '#a78bfa', text: '#6d28d9', tag: '#8b5cf6' },
  'Fulfillment':    { bg: '#f0fdfa', border: '#5eead4', text: '#0f766e', tag: '#14b8a6' },
  'Shipping':       { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8', tag: '#3b82f6' },
  'Billing':        { bg: '#fffbeb', border: '#fcd34d', text: '#a16207', tag: '#d97706' },
  'Notifications':  { bg: '#fdf2f8', border: '#f9a8d4', text: '#9d174d', tag: '#db2777' },
  'Analytics':      { bg: '#f0f9ff', border: '#7dd3fc', text: '#0369a1', tag: '#0ea5e9' },
  'Compliance':     { bg: '#f8fafc', border: '#94a3b8', text: '#334155', tag: '#64748b' },
  // Generic fallbacks
  Finance:   { bg: '#f5f3ff', border: '#a78bfa', text: '#6d28d9', tag: '#8b5cf6' },
  Ops:       { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8', tag: '#3b82f6' },
  IT:        { bg: '#f0fdfa', border: '#5eead4', text: '#0f766e', tag: '#14b8a6' },
  HR:        { bg: '#fdf2f8', border: '#f9a8d4', text: '#9d174d', tag: '#db2777' },
  Sales:     { bg: '#fffbeb', border: '#fcd34d', text: '#a16207', tag: '#d97706' },
  default:   { bg: '#f8fafc', border: '#94a3b8', text: '#475569', tag: '#64748b' },
}

function deptColor(dept) {
  return DEPT_COLORS[dept] ?? DEPT_COLORS.default
}

// ---------------------------------------------------------------------------
// Actor icons
// ---------------------------------------------------------------------------
const ACTOR_CONFIG = {
  human:      { icon: User,  color: '#78716c', label: 'Human' },
  ai_agent:   { icon: Bot,   color: '#71717a', label: 'AI Agent' },
  automated:  { icon: Zap,   color: '#64748b', label: 'Automated' },
  external:   { icon: Globe, color: '#78716c', label: 'External' },
}

function getActorType(actors) {
  if (!actors || actors.length === 0) return 'automated'
  return actors[0]?.type || 'automated'
}

// ---------------------------------------------------------------------------
// Mock graph data for when API is unavailable
// ---------------------------------------------------------------------------
const MOCK_GRAPH = {
  nodes: [
    { id: 'FIN-001', data: { rule_id: 'FIN-001', title: 'Invoice threshold check', department: 'Finance', risk_level: 'high',     status: 'active', owner: 'alice' } },
    { id: 'FIN-002', data: { rule_id: 'FIN-002', title: 'Payment approval gate',   department: 'Finance', risk_level: 'critical', status: 'active', owner: 'alice' } },
    { id: 'OPS-001', data: { rule_id: 'OPS-001', title: 'Queue depth monitor',     department: 'Ops',     risk_level: 'medium',   status: 'active', owner: 'bob' } },
    { id: 'OPS-002', data: { rule_id: 'OPS-002', title: 'Auto-scale trigger',      department: 'Ops',     risk_level: 'high',     status: 'active', owner: 'bob' } },
    { id: 'IT-001',  data: { rule_id: 'IT-001',  title: 'Auth rate limit',         department: 'IT',      risk_level: 'critical', status: 'active', owner: 'carol' } },
    { id: 'IT-002',  data: { rule_id: 'IT-002',  title: 'Cert expiry alert',       department: 'IT',      risk_level: 'high',     status: 'active', owner: 'carol' } },
  ],
  edges: [
    { id: 'e1', source: 'FIN-001', target: 'FIN-002' },
    { id: 'e2', source: 'OPS-001', target: 'OPS-002' },
    { id: 'e3', source: 'IT-001',  target: 'IT-002' },
    { id: 'e4', source: 'IT-001',  target: 'FIN-001' },
    { id: 'e5', source: 'OPS-002', target: 'FIN-001' },
  ],
}

// ---------------------------------------------------------------------------
// Dagre layout
// ---------------------------------------------------------------------------

const NODE_W = 240
const NODE_H = 88

function applyDagreLayout(nodes, edges) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir: 'LR',
    nodesep: 50,
    ranksep: 100,
    marginx: 40,
    marginy: 40,
  })

  nodes.forEach(n => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach(e => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return nodes.map(n => {
    const pos = g.node(n.id)
    return {
      ...n,
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
    }
  })
}

// ---------------------------------------------------------------------------
// Custom node component
// ---------------------------------------------------------------------------

function RuleNode({ data, selected }) {
  const { rule_id, title, department, risk_level, status, owner, highlighted, dimmed } = data
  const dc = deptColor(department)

  return (
    <div
      className={clsx(
        'rounded-xl border-2 bg-white shadow-sm transition-all duration-150',
        'w-[240px] overflow-hidden',
        selected  && 'ring-2 ring-slate-300 ring-offset-1',
        dimmed    && 'opacity-25',
        !dimmed && highlighted === 'upstream'   && 'border-slate-400 shadow-sm',
        !dimmed && highlighted === 'downstream' && 'border-slate-500 shadow-sm',
        !dimmed && highlighted === 'self'        && 'border-slate-500 shadow-sm',
        !dimmed && !highlighted && 'border-slate-200 hover:border-slate-300 hover:shadow-sm'
      )}
    >
      {/* Department color strip */}
      <div className="h-1 w-full" style={{ backgroundColor: dc.tag }} />

      <div className="px-3 py-2.5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-1">
          <code className="font-mono text-[10px] text-slate-400 flex-shrink-0 mt-0.5">
            {rule_id}
          </code>
          <div className="flex items-center gap-1">
            <RiskDot level={risk_level} />
            <StatusBadge status={status} size="sm" showIcon={false} />
          </div>
        </div>

        {/* Title */}
        <p
          className="text-xs font-semibold text-slate-800 leading-snug mt-1 line-clamp-2"
          title={title}
        >
          {title}
        </p>

        {/* Footer */}
        <div className="flex items-center justify-between mt-2">
          <span
            className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
            style={{ color: dc.text, backgroundColor: dc.bg, border: `1px solid ${dc.border}33` }}
          >
            {department}
          </span>
          {owner && (
            <span className="flex items-center gap-0.5 text-[10px] text-slate-400">
              <User size={9} />
              {owner}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

const NODE_TYPES = { ruleNode: RuleNode }

// ---------------------------------------------------------------------------
// Build ReactFlow nodes/edges from raw graph data
// ---------------------------------------------------------------------------

function buildFlowElements(graphData, highlightedId, hoveredId) {
  if (!graphData) return { nodes: [], edges: [] }

  const upstreamSet   = new Set()
  const downstreamSet = new Set()

  if (hoveredId) {
    // BFS upstream
    const upQ = [hoveredId]
    while (upQ.length) {
      const cur = upQ.shift()
      graphData.edges.forEach(e => {
        if (e.target === cur && !upstreamSet.has(e.source)) {
          upstreamSet.add(e.source)
          upQ.push(e.source)
        }
      })
    }
    // BFS downstream
    const downQ = [hoveredId]
    while (downQ.length) {
      const cur = downQ.shift()
      graphData.edges.forEach(e => {
        if (e.source === cur && !downstreamSet.has(e.target)) {
          downstreamSet.add(e.target)
          downQ.push(e.target)
        }
      })
    }
  }

  const anyHighlight = hoveredId && (upstreamSet.size > 0 || downstreamSet.size > 0)

  const rawNodes = graphData.nodes.map(n => {
    const isHovered    = n.id === hoveredId
    const isUpstream   = upstreamSet.has(n.id)
    const isDownstream = downstreamSet.has(n.id)
    const isDimmed     = anyHighlight && !isHovered && !isUpstream && !isDownstream

    return {
      id:   n.id,
      type: 'ruleNode',
      data: {
        ...n.data,
        highlighted: isHovered ? 'self' : isUpstream ? 'upstream' : isDownstream ? 'downstream' : null,
        dimmed: isDimmed,
      },
    }
  })

  const flowNodes = applyDagreLayout(rawNodes, graphData.edges)

  const flowEdges = graphData.edges.map(e => {
    const isHighlighted =
      (hoveredId && (e.source === hoveredId || e.target === hoveredId)) ||
      (upstreamSet.has(e.source) && (e.target === hoveredId || upstreamSet.has(e.target))) ||
      (downstreamSet.has(e.target) && (e.source === hoveredId || downstreamSet.has(e.source)))

    const isUpstreamEdge   = upstreamSet.has(e.source) && (e.target === hoveredId || upstreamSet.has(e.target))

    const edgeColor = isHighlighted
      ? '#94a3b8'
      : '#cbd5e1'

    return {
      id:           e.id,
      source:       e.source,
      target:       e.target,
      type:         'smoothstep',
      animated:     isHighlighted,
      markerEnd:    {
        type: MarkerType.ArrowClosed,
        width: 16,
        height: 16,
        color: edgeColor,
      },
      style: {
        strokeWidth: isHighlighted ? 2.5 : 1.5,
        stroke: edgeColor,
        opacity: anyHighlight && !isHighlighted ? 0.15 : 1,
      },
    }
  })

  return { nodes: flowNodes, edges: flowEdges }
}

// ---------------------------------------------------------------------------
// Department filter chips
// ---------------------------------------------------------------------------

function DeptFilter({ departments, active, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <button
        onClick={() => onChange('')}
        className={clsx(
          'text-xs px-2 py-1 rounded-md border font-medium transition-colors',
          !active ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
        )}
      >
        All
      </button>
      {departments.map(dept => {
        const dc = deptColor(dept)
        const isActive = active === dept
        return (
          <button
            key={dept}
            onClick={() => onChange(isActive ? '' : dept)}
            className="text-xs px-2 py-1 rounded-md border font-medium transition-colors"
            style={isActive ? {
              backgroundColor: dc.tag,
              color: 'white',
              borderColor: dc.tag,
            } : {
              backgroundColor: dc.bg,
              color: dc.text,
              borderColor: dc.border + '66',
            }}
          >
            {dept}
          </button>
        )
      })}
    </div>
  )
}

// ===========================================================================
// PIPELINE VIEW
// ===========================================================================

// Pipeline phases — derived dynamically from the rules' departments,
// ordered by the natural lifecycle flow. Unknown departments go at the end.
const DEPT_ORDER = [
  'Order Intake',
  'Fulfillment',
  'Shipping',
  'Billing',
  'Notifications',
  'Analytics',
  'Compliance',
]

function orderDepartments(departments) {
  const ordered = DEPT_ORDER.filter(d => departments.includes(d))
  const extra = departments.filter(d => !DEPT_ORDER.includes(d)).sort()
  return [...ordered, ...extra]
}

function PipelineView({ rules, onSelectRule, selectedRuleId }) {
  const [expandedDepts, setExpandedDepts] = useState(new Set())

  // Group rules by department
  const grouped = useMemo(() => {
    const map = {}
    for (const rule of rules) {
      const dept = rule.department || 'Other'
      if (!map[dept]) map[dept] = []
      map[dept].push(rule)
    }
    return map
  }, [rules])

  const departments = useMemo(() => orderDepartments(Object.keys(grouped)), [grouped])

  // Auto-expand all on mount
  useEffect(() => {
    setExpandedDepts(new Set(departments))
  }, [departments])

  const toggleDept = (dept) => {
    setExpandedDepts(prev => {
      const next = new Set(prev)
      if (next.has(dept)) next.delete(dept)
      else next.add(dept)
      return next
    })
  }

  // Sort rules within a department by upstream → downstream flow
  const sortedRules = useCallback((deptRules) => {
    // Topological-ish sort: rules with no upstream first
    const ruleIds = new Set(deptRules.map(r => r.rule_id))
    const inDegree = {}
    deptRules.forEach(r => { inDegree[r.rule_id] = 0 })
    deptRules.forEach(r => {
      (r.upstream_rule_ids || []).forEach(uid => {
        if (ruleIds.has(uid)) {
          inDegree[r.rule_id] = (inDegree[r.rule_id] || 0) + 1
        }
      })
    })
    return [...deptRules].sort((a, b) => (inDegree[a.rule_id] || 0) - (inDegree[b.rule_id] || 0))
  }, [])

  const RISK_PILL = { critical: 'crit', high: 'high', medium: 'med', low: 'low' }

  return (
    <div style={{
      display: 'flex',
      height: '100%',
      overflowX: 'auto',
      overflowY: 'hidden',
      background: 'var(--paper)',
    }}>
      {departments.map((dept, deptIdx) => {
        const deptRules = sortedRules(grouped[dept] || [])
        const isExpanded = expandedDepts.has(dept)
        const activeCount = deptRules.filter(r => r.status === 'active').length
        const riskCounts = {}
        deptRules.forEach(r => {
          riskCounts[r.risk_level] = (riskCounts[r.risk_level] || 0) + 1
        })

        return (
          <div
            key={dept}
            style={{
              display: 'flex',
              flexDirection: 'column',
              flexShrink: 0,
              width: 300,
              minWidth: 300,
              borderRight: deptIdx < departments.length - 1 ? '1px solid var(--rule-hair)' : 'none',
              background: 'var(--vellum)',
            }}
          >
            {/* Phase header — editorial style, small folio-caps */}
            <div
              onClick={() => toggleDept(dept)}
              style={{
                flexShrink: 0,
                padding: '14px 16px 12px',
                cursor: 'pointer',
                userSelect: 'none',
                borderBottom: '1px solid var(--rule)',
                background: 'var(--paper-2)',
                transition: 'background 120ms',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
                  <span className="eyebrow" style={{ fontSize: 10 }}>§ {deptIdx + 1}</span>
                  <h3 className="display" style={{
                    fontSize: 15, margin: 0, color: 'var(--ink)',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {dept}
                  </h3>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--ink-3)' }}>
                  <span style={{ fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>{deptRules.length}</span>
                  {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 10.5, color: 'var(--ink-4)' }}>{activeCount} active</span>
                {riskCounts.critical > 0 && (
                  <span className="pill crit" style={{ fontSize: 9.5, padding: '1px 5px' }}>
                    {riskCounts.critical} critical
                  </span>
                )}
                {riskCounts.high > 0 && (
                  <span className="pill high" style={{ fontSize: 9.5, padding: '1px 5px' }}>
                    {riskCounts.high} high
                  </span>
                )}
              </div>
            </div>

            {/* Rules list */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '10px 10px 14px' }}>
              {isExpanded && deptRules.map((rule, ruleIdx) => {
                const actorType = getActorType(rule.actors)
                const actor = ACTOR_CONFIG[actorType] || ACTOR_CONFIG.automated
                const ActorIcon = actor.icon
                const isSelected = selectedRuleId === rule.rule_id
                const riskClass = RISK_PILL[rule.risk_level]

                return (
                  <div key={rule.rule_id}>
                    <div
                      onClick={() => onSelectRule?.(rule)}
                      style={{
                        padding: '10px 12px',
                        cursor: 'pointer',
                        background: isSelected ? 'var(--accent-wash)' : 'var(--vellum)',
                        border: isSelected
                          ? '1px solid var(--accent)'
                          : '1px solid var(--rule-soft)',
                        borderRadius: 'var(--radius)',
                        transition: 'border-color 80ms, background 80ms',
                      }}
                    >
                      {/* Step number + title */}
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                        <div style={{
                          flexShrink: 0,
                          width: 20, height: 20,
                          borderRadius: '50%',
                          border: '1px solid var(--rule)',
                          background: 'var(--paper-2)',
                          color: 'var(--ink-4)',
                          fontSize: 10, fontWeight: 600,
                          fontFamily: 'var(--ff-mono)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          marginTop: 1,
                        }}>
                          {ruleIdx + 1}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{
                            margin: 0,
                            fontSize: 12.5,
                            fontWeight: 500,
                            color: 'var(--ink)',
                            lineHeight: 1.35,
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}>
                            {rule.title}
                          </p>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4, color: 'var(--ink-4)' }}>
                            <ActorIcon size={10} />
                            <span style={{ fontSize: 10 }}>{actor.label}</span>
                            <span style={{ color: 'var(--ink-5)' }}>·</span>
                            <code className="mono" style={{ fontSize: 9.5, color: 'var(--ink-4)' }}>
                              {rule.rule_id}
                            </code>
                          </div>
                        </div>
                      </div>

                      {rule.description && (
                        <p style={{
                          margin: '6px 0 0 30px',
                          fontSize: 10.5, color: 'var(--ink-3)',
                          lineHeight: 1.45,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}>
                          {rule.description}
                        </p>
                      )}

                      {/* Tags row */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 8, marginLeft: 30, flexWrap: 'wrap' }}>
                        {rule.status && (
                          <span className={`pill ${rule.status === 'active' ? 'active' : rule.status === 'paused' ? 'paused' : 'planned'}`}
                                style={{ fontSize: 9.5, padding: '1px 5px' }}>
                            <span className="dot" />{rule.status}
                          </span>
                        )}
                        {riskClass && (
                          <span className={`pill ${riskClass}`} style={{ fontSize: 9.5, padding: '1px 5px' }}>
                            {rule.risk_level}
                          </span>
                        )}
                        {rule.editable_fields?.length > 0 && (
                          <span className="pill planned" style={{ fontSize: 9.5, padding: '1px 5px' }}>
                            {rule.editable_fields.length} editable
                          </span>
                        )}
                        {rule.customer_facing && (
                          <span className="pill planned" style={{ fontSize: 9.5, padding: '1px 5px' }}>
                            customer
                          </span>
                        )}
                      </div>

                      {/* Downstream links */}
                      {rule.downstream_rule_ids?.length > 0 && (
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6, marginLeft: 30 }}>
                          {rule.downstream_rule_ids.map(did => (
                            <code key={did}
                                  className="mono"
                                  title={`Downstream: ${did}`}
                                  style={{
                                    fontSize: 9.5,
                                    padding: '1px 5px',
                                    borderRadius: 3,
                                    border: '1px solid var(--rule-soft)',
                                    background: 'var(--paper-2)',
                                    color: 'var(--ink-4)',
                                  }}>
                              → {did}
                            </code>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Connector arrow between rules */}
                    {ruleIdx < deptRules.length - 1 && (
                      <div style={{ display: 'flex', justifyContent: 'center', padding: '4px 0' }}>
                        <ArrowDown size={13} style={{ color: 'var(--ink-5)' }} />
                      </div>
                    )}
                  </div>
                )
              })}

              {isExpanded && deptRules.length === 0 && (
                <div style={{
                  padding: '32px 12px',
                  textAlign: 'center',
                  color: 'var(--ink-4)',
                  fontSize: 11.5,
                  fontStyle: 'italic',
                }}>
                  No rules in this department
                </div>
              )}
            </div>

            {/* Phase footer — forward arrow */}
            {deptIdx < departments.length - 1 && (
              <div style={{
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                padding: '6px 10px',
                borderTop: '1px solid var(--rule-hair)',
              }}>
                <ArrowRight size={14} style={{ color: 'var(--ink-5)' }} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ===========================================================================
// SELECTED RULE DETAIL PANEL (shared between views)
// ===========================================================================

function RuleDetailPanel({ rule, onClose }) {
  if (!rule) return null
  const dc = deptColor(rule.department)

  return (
    <div className="
      absolute top-4 left-4 w-72 bg-white rounded-xl border border-slate-200
      shadow-lg p-4 space-y-3 z-10
    " style={{ animation: 'fadeIn 0.15s ease-out' }}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <code className="font-mono text-[10px] text-slate-400">{rule.rule_id}</code>
          <h3 className="text-sm font-semibold text-slate-800 mt-0.5 leading-snug">
            {rule.title}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="flex-shrink-0 p-0.5 text-slate-400 hover:text-slate-600 transition-colors"
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <StatusBadge status={rule.status} size="sm" />
        <RiskBadge level={rule.risk_level} size="sm" />
      </div>

      {rule.why && (
        <p className="text-xs text-slate-600 leading-relaxed border-l-2 border-slate-200 pl-2">
          {rule.why}
        </p>
      )}

      <div className="space-y-1 text-xs">
        <div className="flex justify-between">
          <span className="text-slate-500">Department</span>
          <span className="font-medium text-slate-700">{rule.department}</span>
        </div>
        {rule.owner && (
          <div className="flex justify-between">
            <span className="text-slate-500">Owner</span>
            <span className="font-medium text-slate-700">{rule.owner}</span>
          </div>
        )}
        {rule.editable_fields?.length > 0 && (
          <div className="flex justify-between">
            <span className="text-slate-500">Editable fields</span>
            <span className="font-medium text-slate-700">{rule.editable_fields.length}</span>
          </div>
        )}
      </div>

      {rule.trigger && (
        <div className="text-xs">
          <span className="text-slate-500 font-medium">Trigger: </span>
          <span className="text-slate-700">{rule.trigger}</span>
        </div>
      )}

      <p className="text-[10px] text-slate-400 pt-1 border-t border-slate-100">
        Click a rule for full detail in the registry.
      </p>
    </div>
  )
}

// ===========================================================================
// GraphPage — main component with DAG + Pipeline view toggle
// ===========================================================================

export default function GraphPage() {
  const [viewMode, setViewMode] = useState(VIEW_PIPELINE)
  const [graphData, setGraphData] = useState(null)
  const [allRules, setAllRules] = useState([])
  const [loading, setLoading]     = useState(true)
  const [deptFilter, setDeptFilter] = useState('')
  const [hoveredId, setHoveredId]   = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [selectedRule, setSelectedRule] = useState(null)

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  // Load graph + full rules
  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [graphResult, rulesResult] = await Promise.allSettled([
        getGraph(),
        getRules({ limit: 500 }),
      ])
      setGraphData(graphResult.status === 'fulfilled' ? graphResult.value : MOCK_GRAPH)
      if (rulesResult.status === 'fulfilled') {
        setAllRules(rulesResult.value?.items || rulesResult.value || [])
      }
    } catch {
      setGraphData(MOCK_GRAPH)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // Compute filtered + laid-out graph
  const filteredGraph = useMemo(() => {
    if (!graphData) return null
    const filteredNodes = deptFilter
      ? graphData.nodes.filter(n => n.data.department === deptFilter)
      : graphData.nodes
    const filteredNodeIds = new Set(filteredNodes.map(n => n.id))
    const filteredEdges = graphData.edges.filter(
      e => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)
    )
    return { nodes: filteredNodes, edges: filteredEdges }
  }, [graphData, deptFilter])

  useEffect(() => {
    if (!filteredGraph || viewMode !== VIEW_DAG) return
    const { nodes: n, edges: e } = buildFlowElements(filteredGraph, selectedId, hoveredId)
    setNodes(n)
    setEdges(e)
  }, [filteredGraph, hoveredId, selectedId, viewMode])

  const departments = useMemo(() => {
    if (!graphData) return []
    return [...new Set(graphData.nodes.map(n => n.data.department))].sort()
  }, [graphData])

  const handleNodeClick = useCallback((_, node) => {
    setSelectedId(node.id)
    setSelectedRule(node.data)
  }, [])

  const handleNodeMouseEnter = useCallback((_, node) => setHoveredId(node.id), [])
  const handleNodeMouseLeave = useCallback(() => setHoveredId(null), [])
  const handlePaneClick = useCallback(() => {
    setSelectedId(null)
    setSelectedRule(null)
  }, [])

  const handlePipelineSelectRule = useCallback((rule) => {
    setSelectedId(rule.rule_id)
    setSelectedRule(rule)
  }, [])

  return (
    <>
      <header className="page-head">
        <div>
          <div className="folio">§ III · Process Flow</div>
          <h1>Process <em>flow</em></h1>
          <div className="lede">
            How rules depend on one another. Columns are departments; color indicates risk tier.
          </div>
        </div>
        <div className="head-actions">
          <button
            className={`btn sm ${viewMode === VIEW_PIPELINE ? 'primary' : ''}`}
            onClick={() => setViewMode(VIEW_PIPELINE)}
          >
            Pipeline
          </button>
          <button
            className={`btn sm ${viewMode === VIEW_DAG ? 'primary' : ''}`}
            onClick={() => setViewMode(VIEW_DAG)}
          >
            DAG
          </button>
          <button className="btn sm" onClick={loadData} title="Reload">Reload</button>
        </div>
      </header>

      {viewMode === VIEW_DAG && (
        <div className="pf-legend">
          <span><span className="sw" style={{ background: 'var(--risk-crit)' }} />Critical</span>
          <span><span className="sw" style={{ background: 'var(--risk-high)' }} />High</span>
          <span><span className="sw" style={{ background: 'var(--risk-med)' }} />Medium</span>
          <span><span className="sw" style={{ background: 'var(--risk-low)' }} />Low</span>
          <div className="l-row gap8" style={{ marginLeft: 'auto', flexWrap: 'wrap' }}>
            <span className="dim" style={{ fontSize: 11.5, marginRight: 4 }}>Dept:</span>
            <DeptFilter
              departments={departments}
              active={deptFilter}
              onChange={setDeptFilter}
            />
          </div>
        </div>
      )}

      {loading ? (
        <div
          className="l-card"
          style={{ padding: 60, textAlign: 'center', color: 'var(--ink-3)' }}
        >
          Building process graph…
        </div>
      ) : (
      <div
        className="l-card"
        style={{ padding: 0, overflow: 'hidden', height: 640, position: 'relative' }}
      >
        {/* ---- DAG VIEW ---- */}
        {viewMode === VIEW_DAG && (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={NODE_TYPES}
            onNodeClick={handleNodeClick}
            onNodeMouseEnter={handleNodeMouseEnter}
            onNodeMouseLeave={handleNodeMouseLeave}
            onPaneClick={handlePaneClick}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.2}
            maxZoom={2}
          >
            <Background color="#e2e8f0" gap={20} size={1} />
            <Controls className="!shadow-sm !border-slate-200" />
            <MiniMap
              nodeColor={n => deptColor(n.data?.department).tag}
              maskColor="rgba(248,250,252,0.8)"
              className="!border-slate-200 !shadow-sm"
            />

            {/* Stats panel */}
            <Panel position="top-right">
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm px-4 py-3 text-xs text-slate-600 space-y-1">
                <p className="font-semibold text-slate-700">
                  {filteredGraph?.nodes.length ?? 0} rules
                </p>
                <p className="text-slate-400">
                  {filteredGraph?.edges.length ?? 0} connections
                </p>
                {deptFilter && (
                  <p className="text-slate-600 font-medium">{deptFilter} only</p>
                )}
              </div>
            </Panel>
          </ReactFlow>
        )}

        {/* ---- PIPELINE VIEW ---- */}
        {viewMode === VIEW_PIPELINE && (
          <PipelineView
            rules={allRules}
            onSelectRule={handlePipelineSelectRule}
            selectedRuleId={selectedId}
          />
        )}

        {/* Selected rule detail panel */}
        {selectedRule && (
          <RuleDetailPanel
            rule={selectedRule}
            onClose={() => { setSelectedId(null); setSelectedRule(null) }}
          />
        )}
      </div>
      )}
    </>
  )
}
