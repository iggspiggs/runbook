import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BookOpen, GitFork, Edit2, Shield, Zap, CheckCircle2,
  ArrowRight, AlertTriangle, BarChart2, Flame, ChevronRight,
} from 'lucide-react'
import clsx from 'clsx'
import { getDashboardStats } from '../../api/client.js'

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_STATS = {
  total_rules:      142,
  active_rules:     118,
  unverified_rules:  23,
  departments: [
    { name: 'Finance',   count: 31, rules: { active: 22, unverified: 6, inactive: 3 } },
    { name: 'Ops',       count: 28, rules: { active: 20, unverified: 5, inactive: 3 } },
    { name: 'IT',        count: 24, rules: { active: 18, unverified: 4, inactive: 2 } },
    { name: 'HR',        count: 19, rules: { active: 13, unverified: 4, inactive: 2 } },
    { name: 'Sales',     count: 16, rules: { active: 12, unverified: 2, inactive: 2 } },
    { name: 'Marketing', count: 12, rules: { active: 9,  unverified: 2, inactive: 1 } },
    { name: 'Legal',     count:  8, rules: { active: 6,  unverified: 1, inactive: 1 } },
    { name: 'Other',     count:  4, rules: { active: 3,  unverified: 1, inactive: 0 } },
  ],
  risk_distribution: { low: 68, medium: 47, high: 21, critical: 6 },
}

// ---------------------------------------------------------------------------
// How-it-works steps
// ---------------------------------------------------------------------------

const STEPS = [
  {
    num:     1,
    icon:    Zap,
    title:   'Extract',
    color:   'text-slate-700 bg-slate-50 border-slate-200',
    summary: 'Point the extractor at your codebase.',
    detail:  'The AI parser scans your Python, JavaScript, YAML, and config files to identify automation rules — thresholds, triggers, approval chains, retry policies, and more — and converts them into structured entries.',
  },
  {
    num:     2,
    icon:    BookOpen,
    title:   'Registry',
    color:   'text-slate-700 bg-slate-50 border-slate-200',
    summary: 'Every rule lives in one place.',
    detail:  'Extracted rules are stored in a searchable registry with full metadata: owner, department, risk level, status, source file, and upstream/downstream dependencies. Nothing is hidden in a script anymore.',
  },
  {
    num:     3,
    icon:    Edit2,
    title:   'Edit safely',
    color:   'text-slate-700 bg-slate-50 border-slate-200',
    summary: 'Change values without touching code.',
    detail:  'Each rule exposes "editable fields" — the parameters operators are allowed to tune. Use the what-if simulator to preview the blast radius before saving. All changes are logged to the immutable audit trail.',
  },
  {
    num:     4,
    icon:    Shield,
    title:   'Verify',
    color:   'text-slate-700 bg-slate-50 border-slate-200',
    summary: 'A human eyes each extracted rule.',
    detail:  'The AI gives each rule a confidence score. Until a human operator reviews and marks it verified, the rule is flagged as unconfirmed. Verification proves that a real person understands what the rule does.',
  },
  {
    num:     5,
    icon:    GitFork,
    title:   'Process Flow',
    color:   'text-slate-700 bg-slate-50 border-slate-200',
    summary: 'See how rules connect.',
    detail:  'The process graph shows upstream and downstream dependencies between rules as a live DAG. Hover any node to trace the entire chain that feeds into it — or everything it affects.',
  },
]

// ---------------------------------------------------------------------------
// Step circle
// ---------------------------------------------------------------------------

function StepCircle({ step, isActive, isCompleted }) {
  if (isCompleted) {
    return (
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
        <CheckCircle2 size={16} className="text-white" />
      </div>
    )
  }
  if (isActive) {
    return (
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 border border-slate-600 flex items-center justify-center">
        <span className="text-sm font-bold text-white leading-none">{step.num}</span>
      </div>
    )
  }
  return (
    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-200 border border-slate-200 flex items-center justify-center">
      <span className="text-sm font-bold text-slate-600 leading-none">{step.num}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// StepCard
// ---------------------------------------------------------------------------

function StepCard({ step, active, completed, onClick }) {
  const { Icon } = step
  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex items-start gap-3 text-left rounded-xl border p-4 transition-all duration-150',
        'w-full group',
        active
          ? step.color + ' shadow-sm'
          : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-sm'
      )}
    >
      <StepCircle step={step} isActive={active} isCompleted={completed} />
      <div className="flex-1 min-w-0">
        <p className={clsx('text-sm font-semibold', active ? '' : 'text-slate-700')}>{step.title}</p>
        <p className={clsx('text-xs mt-0.5', active ? 'opacity-75' : 'text-slate-500')}>
          {step.summary}
        </p>
      </div>
      <ChevronRight size={14} className={clsx('flex-shrink-0 mt-1', active ? 'opacity-60' : 'text-slate-300 group-hover:text-slate-500')} />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Mini bar chart
// ---------------------------------------------------------------------------

function MiniBarChart({ rules, total }) {
  if (!total) return null
  const bars = [
    { label: 'Active',     count: rules.active,     color: 'bg-slate-400' },
    { label: 'Unverified', count: rules.unverified,  color: 'bg-amber-300' },
    { label: 'Inactive',   count: rules.inactive,    color: 'bg-slate-200' },
  ]
  return (
    <div className="mt-3 space-y-1.5">
      {bars.map(bar => (
        <div key={bar.label} className="flex items-center gap-2">
          <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
            <div
              className={clsx('h-full rounded-full transition-all duration-500', bar.color)}
              style={{ width: `${(bar.count / total) * 100}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-400 w-14 text-right flex-shrink-0 tabular-nums">
            {bar.count} {bar.label}
          </span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Department card
// ---------------------------------------------------------------------------

function DeptCard({ dept, navigate }) {
  return (
    <button
      onClick={() => navigate(`/registry?department=${dept.name}`)}
      className="stat-card text-left border border-slate-200 hover:border-slate-300 hover:shadow-sm transition-all duration-150 group"
    >
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm font-semibold text-slate-700">{dept.name}</p>
        <ChevronRight size={12} className="text-slate-300 group-hover:text-slate-500 transition-colors" />
      </div>
      <p className="text-2xl font-bold text-slate-900 tabular-nums">{dept.count}</p>
      <p className="text-xs text-slate-400">rules</p>
      {dept.rules && (
        <MiniBarChart rules={dept.rules} total={dept.count} />
      )}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Suggestion card — actionable card with arrow
// ---------------------------------------------------------------------------

function SuggestionCard({ icon: Icon, title, desc, action, onClick, accent = 'amber' }) {
  const accentMap = {
    amber:  { icon: 'text-amber-600' },
    red:    { icon: 'text-red-500' },
    indigo: { icon: 'text-slate-500' },
  }
  const a = accentMap[accent] ?? accentMap.indigo
  return (
    <div className="rounded-xl border border-slate-200 bg-white hover:border-slate-300 p-4 flex flex-col gap-3 transition-colors">
      <div className="flex items-start gap-2">
        <div className={clsx('flex-shrink-0 w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center border border-slate-200', a.icon)}>
          <Icon size={16} />
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-700">{title}</p>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{desc}</p>
        </div>
      </div>
      <button
        onClick={onClick}
        className="flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 transition-colors"
      >
        <span>{action}</span>
        <ArrowRight size={12} />
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// OnboardingPage
// ---------------------------------------------------------------------------

export default function OnboardingPage() {
  const navigate               = useNavigate()
  const [stats, setStats]      = useState(MOCK_STATS)
  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    getDashboardStats().then(setStats).catch(() => setStats(MOCK_STATS))
  }, [])

  const s              = stats ?? MOCK_STATS
  const totalRules     = s.total_rules ?? 0
  const deptCount      = (s.departments ?? []).length
  const unverified     = s.unverified_rules ?? 0
  const verifiedCount  = totalRules - unverified
  const verifiedPct    = totalRules > 0 ? Math.round((verifiedCount / totalRules) * 100) : 0
  const highRisk       = (s.risk_distribution?.high ?? 0) + (s.risk_distribution?.critical ?? 0)

  const currentStep    = STEPS[activeStep]
  const { Icon: CurrentIcon } = currentStep

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8">

      {/* Hero banner */}
      <div className="rounded-2xl bg-gradient-to-br from-slate-800 to-indigo-900 text-white overflow-hidden">
        <div className="p-6 space-y-3">
          <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <BookOpen size={13} />
            Getting Started
          </div>
          <h1 className="text-2xl font-bold leading-snug text-balance">
            Your system has{' '}
            <span className="text-slate-300">{totalRules.toLocaleString()} automation rules</span>
            {' '}across{' '}
            <span className="text-slate-300">{deptCount} departments</span>
          </h1>
          <p className="text-sm text-slate-400 max-w-2xl leading-relaxed">
            Runbook gives operators a living registry of every automation rule that governs your
            systems — where they come from, what they do, who owns them, and how they connect.
            This guide walks you through the platform in five steps.
          </p>

          {/* Verification progress bar */}
          <div className="mt-4 space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400">Team verification progress</span>
              <span className="font-semibold text-white">{verifiedPct}% verified</span>
            </div>
            <div className="relative h-2 bg-white/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-slate-700 rounded-full transition-all duration-700"
                style={{ width: `${verifiedPct}%` }}
                role="progressbar"
                aria-valuenow={verifiedPct}
                aria-label="Verification progress"
              />
            </div>
            <p className="text-xs text-slate-500">
              {verifiedCount} of {totalRules} rules reviewed · {unverified} still need a human eye
            </p>
          </div>
        </div>
      </div>

      {/* How it works — interactive steps */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Step list */}
        <div className="space-y-2">
          {STEPS.map((step, i) => (
            <StepCard
              key={step.num}
              step={step}
              active={activeStep === i}
              completed={i < activeStep}
              onClick={() => setActiveStep(i)}
            />
          ))}
        </div>

        {/* Step detail panel */}
        <div className="lg:col-span-2">
          <div className={clsx(
            'rounded-2xl border p-6 h-full flex flex-col gap-4 animate-fade-in',
            currentStep.color
          )}>
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl bg-white border border-slate-200 flex items-center justify-center">
                <CurrentIcon size={20} />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider opacity-70">
                  Step {currentStep.num} of {STEPS.length}
                </p>
                <h2 className="text-lg font-bold">{currentStep.title}</h2>
              </div>
            </div>
            <p className="text-sm leading-relaxed flex-1">{currentStep.detail}</p>
            <div className="flex items-center gap-2 pt-2 border-t border-black/10">
              {activeStep > 0 && (
                <button
                  onClick={() => setActiveStep(i => i - 1)}
                  className="px-3 py-1.5 rounded-lg bg-white/40 hover:bg-white/60 text-sm font-medium transition-colors"
                >
                  Back
                </button>
              )}
              {activeStep < STEPS.length - 1 && (
                <button
                  onClick={() => setActiveStep(i => i + 1)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/60 hover:bg-white/80 text-sm font-semibold transition-colors"
                >
                  Next <ArrowRight size={14} />
                </button>
              )}
              {activeStep === STEPS.length - 1 && (
                <button
                  onClick={() => navigate('/registry')}
                  className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-white/60 hover:bg-white/80 text-sm font-semibold transition-colors"
                >
                  Open Registry <ArrowRight size={14} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Department cards */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
          Rules by Department — click to explore
        </h3>
        <div className="grid grid-fill-280 gap-3">
          {(s.departments ?? []).map(dept => (
            <DeptCard key={dept.name} dept={dept} navigate={navigate} />
          ))}
        </div>
      </div>

      {/* Start-here suggestions */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
          Start here
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {unverified > 0 && (
            <SuggestionCard
              icon={AlertTriangle}
              title={`${unverified} rules need verification`}
              desc="These rules were extracted automatically and haven't been confirmed by a human yet."
              action="Review unverified rules"
              onClick={() => navigate('/registry?verified=false')}
              accent="amber"
            />
          )}
          {highRisk > 0 && (
            <SuggestionCard
              icon={Flame}
              title={`${highRisk} high or critical risk rules`}
              desc="These rules have a wide blast radius. Understand them before making any changes."
              action="View high-risk rules"
              onClick={() => navigate('/registry?risk_level=high')}
              accent="red"
            />
          )}
          <SuggestionCard
            icon={GitFork}
            title="Explore the process graph"
            desc="See how your automation rules connect to each other in a live dependency DAG."
            action="Open process flow"
            onClick={() => navigate('/graph')}
            accent="indigo"
          />
        </div>
      </div>

    </div>
  )
}
