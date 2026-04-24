import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDashboardStats } from '../../api/client.js'

const MOCK_STATS = {
  total_rules: 142,
  active_rules: 118,
  unverified_rules: 23,
  departments: [
    { name: 'Finance', count: 31 }, { name: 'Operations', count: 28 },
    { name: 'Engineering', count: 24 }, { name: 'People', count: 19 },
    { name: 'Sales', count: 16 }, { name: 'Marketing', count: 12 },
    { name: 'Legal', count: 8 }, { name: 'Other', count: 4 },
  ],
  risk_distribution: { low: 68, medium: 47, high: 21, critical: 6 },
}

const STEPS = [
  {
    n: 1,
    t: 'Enroll your first rule',
    d: 'Rules enter the registry either by filing a form manually, or by running an extraction against your source repository. Either way, they get stamped with a date and owner.',
  },
  {
    n: 2,
    t: 'Run an extraction',
    d: 'Extractions scan source for patterns that look like automations — scheduled tasks, webhook handlers, if-this-then-that triggers — and produce a report you can review.',
  },
  {
    n: 3,
    t: 'Sign rules as you verify',
    d: 'Every rule begins its life unsigned. A steward reads the code, confirms intent, and signs. A signature is not permanent — rules re-enter unsigned state when the underlying code changes.',
  },
  {
    n: 4,
    t: 'Inspect the process graph',
    d: 'The Process Flow view plots rules as a directed graph so you can trace the blast radius of a proposed change before you commit to it.',
  },
  {
    n: 5,
    t: 'Consult the audit log',
    d: 'Nothing is ever silently deleted. Every amendment enters the audit log, signed by the operator who made it, and retained in perpetuity.',
  },
]

const Ic = {
  arrow: <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 6h8M7 3l3 3-3 3"/></svg>,
}

export default function OnboardingPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(MOCK_STATS)

  useEffect(() => {
    getDashboardStats().then(setStats).catch(() => setStats(MOCK_STATS))
  }, [])

  const s = stats ?? MOCK_STATS
  const totalRules = s.total_rules ?? 0
  const deptCount = (s.departments ?? []).length
  const unverified = s.unverified_rules ?? 0
  const highRisk = (s.risk_distribution?.high ?? 0) + (s.risk_distribution?.critical ?? 0)

  return (
    <>
      <header className="page-head">
        <div>
          <div className="folio">§ VIII · Preface</div>
          <h1>Getting <em>started</em></h1>
          <div className="lede">
            A quick orientation for new stewards — how rules enter the registry, how they stay honest, and how to read the process graph.
          </div>
        </div>
        <div className="head-actions">
          <div className="dim" style={{ fontSize: 12.5 }}>8 min read</div>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 40 }}>
        <div>
          {STEPS.map((step, i) => (
            <div key={step.n} className={`gs-step${i === 0 ? ' focus' : ''}`}>
              <div className="gs-num">{step.n}</div>
              <div>
                <h3>{step.t}</h3>
                <p>{step.d}</p>
              </div>
            </div>
          ))}
        </div>

        <aside>
          <div className="l-card" style={{ padding: '16px 18px' }}>
            <div className="card-title" style={{ fontSize: 15, marginBottom: 10 }}>Your registry</div>
            <div className="health" style={{ padding: 0, border: 0, background: 'transparent' }}>
              <div className="row">
                <div className="k">Total rules</div>
                <div className="v">{totalRules.toLocaleString()}</div>
              </div>
              <div className="row">
                <div className="k">Departments</div>
                <div className="v">{deptCount}</div>
              </div>
              <div className="row">
                <div className="k">Awaiting verification</div>
                <div className="v">{unverified.toLocaleString()}</div>
              </div>
              <div className="row">
                <div className="k">High-risk rules</div>
                <div className="v">{highRisk.toLocaleString()}</div>
              </div>
            </div>
            <button
              className="btn primary mt16"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => navigate('/registry')}
            >
              Open registry {Ic.arrow}
            </button>
          </div>

          <div className="l-card mt16" style={{ padding: '16px 18px' }}>
            <div className="card-title" style={{ fontSize: 15, marginBottom: 8 }}>Quick links</div>
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', fontSize: 13.5 }}>
              {[
                { label: 'Anatomy of an extraction', to: '/extractions' },
                { label: 'Writing good rule descriptions', to: '/registry' },
                { label: 'The four risk tiers', to: '/registry?risk_level=critical' },
                { label: 'Operator permissions', to: '/governance' },
                { label: 'Exporting for compliance', to: '/audit' },
              ].map(l => (
                <li
                  key={l.label}
                  onClick={() => navigate(l.to)}
                  style={{
                    padding: '8px 0',
                    borderBottom: '1px solid var(--rule-hair)',
                    display: 'flex', justifyContent: 'space-between',
                    cursor: 'pointer',
                  }}
                >
                  <span>{l.label}</span>
                  <span className="dim">{Ic.arrow}</span>
                </li>
              ))}
            </ul>
          </div>

          <div
            className="l-card mt16"
            style={{
              padding: '16px 18px',
              background: 'var(--paper-2)',
              border: '1px solid var(--rule-soft)',
            }}
          >
            <div style={{
              fontFamily: 'var(--ff-display)', fontSize: 15, fontWeight: 500, marginBottom: 4,
              color: 'var(--ink)',
            }}>
              Need a hand?
            </div>
            <div className="dim" style={{ fontSize: 13 }}>
              Book 15 minutes with an onboarding specialist to walk through your first extraction.
            </div>
            <button className="btn mt16 primary" style={{ fontSize: 12.5 }}>
              Book a session {Ic.arrow}
            </button>
          </div>
        </aside>
      </div>
    </>
  )
}
