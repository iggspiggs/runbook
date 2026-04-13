import React, { useState } from 'react'
import { Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom'
import {
  LayoutDashboard,
  ListFilter,
  GitFork,
  Zap,
  ScrollText,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Settings,
  Bell,
} from 'lucide-react'
import clsx from 'clsx'

// Page imports
import DashboardPage from './pages/dashboard/DashboardPage.jsx'
import RegistryPage from './pages/registry/RegistryPage.jsx'
import GraphPage from './pages/graph/GraphPage.jsx'
import ExtractionsPage from './pages/extractions/ExtractionsPage.jsx'
import AuditPage from './pages/audit/AuditPage.jsx'
import OnboardingPage from './pages/onboarding/OnboardingPage.jsx'

const NAV_ITEMS = [
  { to: '/dashboard',   label: 'Overview',     Icon: LayoutDashboard },
  { to: '/registry',    label: 'Registry',     Icon: ListFilter },
  { to: '/graph',       label: 'Process Flow', Icon: GitFork },
  { to: '/extractions', label: 'Extractions',  Icon: Zap },
  { to: '/audit',       label: 'Audit Log',    Icon: ScrollText },
  { to: '/onboarding',  label: 'Getting Started', Icon: BookOpen },
]

function SidebarLink({ to, label, Icon, collapsed }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-100',
          'group relative',
          isActive
            ? 'bg-white/10 text-white'
            : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* Active indicator bar */}
          {isActive && (
            <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-slate-400 rounded-full -ml-0.5" />
          )}
          <Icon
            size={17}
            className={clsx(
              'flex-shrink-0 transition-colors',
              isActive ? 'text-indigo-400' : 'text-slate-500 group-hover:text-slate-300'
            )}
          />
          {!collapsed && (
            <span className="truncate">{label}</span>
          )}
          {/* Tooltip when collapsed */}
          {collapsed && (
            <span className="
              absolute left-full ml-3 px-2 py-1 rounded-md text-xs font-medium
              bg-slate-700 text-white whitespace-nowrap
              opacity-0 group-hover:opacity-100 pointer-events-none
              transition-opacity z-50 shadow-lg
            ">
              {label}
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}

export default function App() {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()

  // Derive page title from current route
  const currentNav = NAV_ITEMS.find(n => location.pathname.startsWith(n.to))

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Sidebar */}
      <aside
        className={clsx(
          'flex flex-col flex-shrink-0 bg-slate-900 border-r border-slate-800',
          'transition-all duration-300 ease-in-out',
          collapsed ? 'w-14' : 'w-56'
        )}
      >
        {/* Logo */}
        <div className={clsx(
          'flex items-center h-14 px-3 flex-shrink-0',
          'border-b border-slate-800',
          collapsed ? 'justify-center' : 'gap-2.5'
        )}>
          <div className="w-7 h-7 rounded-lg bg-indigo-500 flex items-center justify-center flex-shrink-0">
            <GitFork size={14} className="text-white" />
          </div>
          {!collapsed && (
            <span className="font-semibold text-white tracking-tight text-sm">
              Runbook
            </span>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto p-2 space-y-0.5 scrollbar-thin">
          {NAV_ITEMS.map(item => (
            <SidebarLink
              key={item.to}
              to={item.to}
              label={item.label}
              Icon={item.Icon}
              collapsed={collapsed}
            />
          ))}
        </nav>

        {/* Bottom: settings + collapse toggle */}
        <div className="p-2 border-t border-slate-800 space-y-0.5 flex-shrink-0">
          <SidebarLink to="/settings" label="Settings" Icon={Settings} collapsed={collapsed} />

          <button
            onClick={() => setCollapsed(c => !c)}
            className={clsx(
              'flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium',
              'text-slate-500 hover:bg-white/5 hover:text-slate-300 transition-colors',
              collapsed && 'justify-center'
            )}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed
              ? <ChevronRight size={16} />
              : (
                <>
                  <ChevronLeft size={16} className="flex-shrink-0" />
                  <span className="truncate text-xs">Collapse</span>
                  <span className="ml-auto text-[10px] text-slate-600 font-mono tracking-tight">⌘B</span>
                </>
              )
            }
          </button>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between h-14 px-6 bg-white border-b border-slate-200 flex-shrink-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-slate-500">Runbook</span>
            <span className="text-sm text-slate-300">/</span>
            <h1 className="text-sm font-semibold text-slate-800">
              {currentNav?.label ?? 'Runbook'}
            </h1>
          </div>

          <div className="flex items-center gap-2">
            {/* Notification bell — placeholder */}
            <button
              className="relative p-2 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
              aria-label="Notifications"
            >
              <Bell size={16} />
              {/* Notification dot */}
              <span className="absolute top-1.5 right-1.5 w-1 h-1 bg-red-400 rounded-full" />
            </button>

            {/* User avatar placeholder */}
            <div
              className="relative w-7 h-7 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center group cursor-default"
              aria-label="Operator"
            >
              <span className="text-xs font-semibold text-slate-600">Op</span>
              <span className="
                absolute bottom-full mb-1.5 left-1/2 -translate-x-1/2
                px-2 py-1 rounded-md text-xs font-medium
                bg-slate-800 text-white whitespace-nowrap
                opacity-0 group-hover:opacity-100 pointer-events-none
                transition-opacity z-50 shadow-lg
              ">
                Operator
              </span>
            </div>
          </div>
        </header>

        {/* Page content — scrollable */}
        <main className="flex-1 overflow-auto scrollbar-thin">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/registry" element={<RegistryPage />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/extractions" element={<ExtractionsPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
