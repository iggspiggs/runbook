import React, { useState, useEffect } from 'react'
import { Routes, Route, NavLink, useLocation, useNavigate, Navigate } from 'react-router-dom'
import clsx from 'clsx'

import DashboardPage from './pages/dashboard/DashboardPage.jsx'
import RegistryPage from './pages/registry/RegistryPage.jsx'
import GraphPage from './pages/graph/GraphPage.jsx'
import ExtractionsPage from './pages/extractions/ExtractionsPage.jsx'
import AuditPage from './pages/audit/AuditPage.jsx'
import OnboardingPage from './pages/onboarding/OnboardingPage.jsx'
import DataAccessPage from './pages/data-access/DataAccessPage.jsx'
import GovernancePage from './pages/governance/GovernancePage.jsx'
import CompliancePage from './pages/compliance/CompliancePage.jsx'
import AgentLogsPage from './pages/agent-logs/AgentLogsPage.jsx'
import UserSelector from './components/common/UserSelector.jsx'

// ---------- tiny stroke icon set (16px) ----------
const Ic = {
  grid:    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>,
  list:    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M4 4h9M4 8h9M4 12h9"/><circle cx="2.2" cy="4" r=".6" fill="currentColor"/><circle cx="2.2" cy="8" r=".6" fill="currentColor"/><circle cx="2.2" cy="12" r=".6" fill="currentColor"/></svg>,
  flow:    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="3" cy="8" r="1.6"/><circle cx="13" cy="4" r="1.6"/><circle cx="13" cy="12" r="1.6"/><path d="M4.5 7.2l7 -2.6M4.5 8.8l7 2.6"/></svg>,
  scan:    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M3 3h2M3 3v2M13 3h-2M13 3v2M3 13h2M3 13v-2M13 13h-2M13 13v-2M5 8h6"/></svg>,
  log:     <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="3" y="2.5" width="10" height="11" rx="1"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3"/></svg>,
  book:    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M3 3h5a2 2 0 0 1 2 2v8M13 3H8v10h5V3z"/></svg>,
  shield:  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M8 2l5 2v4c0 3-2.2 5-5 6-2.8-1-5-3-5-6V4l5-2z"/></svg>,
  folder:  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M2 4.5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4.5z"/></svg>,
  archive: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="2" y="3" width="12" height="3" rx="0.5"/><path d="M3 6v7h10V6M6.5 9h3"/></svg>,
  bot:     <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="3" y="5" width="10" height="8" rx="1.5"/><circle cx="6" cy="9" r="0.8" fill="currentColor"/><circle cx="10" cy="9" r="0.8" fill="currentColor"/><path d="M8 3v2M6 13v1M10 13v1"/></svg>,
  search:  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5l3 3"/></svg>,
  bell:    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M4 11v-3a4 4 0 0 1 8 0v3l1 1H3l1 -1z"/><path d="M6.5 13.5a1.5 1.5 0 0 0 3 0"/></svg>,
  moon:    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M12 10a5 5 0 1 1-6-6 4 4 0 0 0 6 6z"/></svg>,
  sun:     <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="8" cy="8" r="3"/><path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1"/></svg>,
}

export const LIcons = Ic

const NAV = [
  { to: '/dashboard',   label: 'Overview',        ico: Ic.grid,    folio: 'I'    },
  { to: '/registry',    label: 'Registry',        ico: Ic.list,    folio: 'II'   },
  { to: '/graph',       label: 'Process Flow',    ico: Ic.flow,    folio: 'III'  },
  { to: '/extractions', label: 'Extractions',     ico: Ic.scan,    folio: 'IV'   },
  { to: '/governance',  label: 'Governance',      ico: Ic.shield,  folio: 'V'    },
  { to: '/compliance',  label: 'Compliance',      ico: Ic.archive, folio: 'VI'   },
  { to: '/data-access', label: 'Data Access',     ico: Ic.folder,  folio: 'VII'  },
  { to: '/audit',       label: 'Audit Log',       ico: Ic.log,     folio: 'VIII' },
  { to: '/agent-logs',  label: 'Agent Logs',      ico: Ic.bot,     folio: 'IX'   },
  { to: '/onboarding',  label: 'Getting Started', ico: Ic.book,    folio: 'X'    },
]

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()

  const [mode, setMode] = useState(() => localStorage.getItem('ledger_mode') || 'light')

  useEffect(() => {
    document.documentElement.dataset.mode = mode
    localStorage.setItem('ledger_mode', mode)
  }, [mode])

  const currentNav = NAV.find(n => location.pathname.startsWith(n.to))
  const crumbTitle = currentNav?.label ?? 'Ledger'

  return (
    <div className="app" data-screen-label={`Ledger · ${currentNav?.label || 'overview'}`}>
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">R</div>
          <div className="brand-name">Runbook</div>
        </div>

        <div className="nav-section">Workspace</div>

        <nav className="nav">
          {NAV.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) => clsx('nav-item', isActive && 'active')}
            >
              <span className="ico">{n.ico}</span>
              <span className="lbl">{n.label}</span>
              <span className="folio">{n.folio}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="org-mark">A</div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 500, color: 'var(--ink)', fontSize: 12.5 }}>Acme, Inc.</div>
            <div style={{ fontSize: 11, color: 'var(--ink-4)' }}>operational registry</div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        <div className="topbar">
          <div className="crumb">
            <span>Runbook</span>
            <span className="sep">/</span>
            <span className="current">{crumbTitle}</span>
          </div>

          <button
            className="search"
            type="button"
            onClick={() => navigate('/registry')}
            aria-label="Search rules"
          >
            {Ic.search}
            <span>Search rules, operators, audit entries…</span>
            <span className="kbd">⌘K</span>
          </button>

          <div className="spacer" />

          <button
            className="icon-btn"
            title={mode === 'night' ? 'Switch to day' : 'Switch to night'}
            onClick={() => setMode(m => (m === 'night' ? 'light' : 'night'))}
          >
            {mode === 'night' ? Ic.sun : Ic.moon}
          </button>

          <button className="icon-btn" title="Notifications" aria-label="Notifications">
            {Ic.bell}
          </button>

          <UserSelector />
        </div>

        <div className="content">
          <div className="content-inner">
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/registry" element={<RegistryPage />} />
              <Route path="/graph" element={<GraphPage />} />
              <Route path="/extractions" element={<ExtractionsPage />} />
              <Route path="/governance" element={<GovernancePage />} />
              <Route path="/compliance" element={<CompliancePage />} />
              <Route path="/data-access" element={<DataAccessPage />} />
              <Route path="/audit" element={<AuditPage />} />
              <Route path="/agent-logs" element={<AgentLogsPage />} />
              <Route path="/onboarding" element={<OnboardingPage />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </div>
        </div>
      </main>
    </div>
  )
}
