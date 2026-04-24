import React, { useEffect, useRef, useState } from 'react'
import { ChevronDown, User as UserIcon, Check } from 'lucide-react'
import clsx from 'clsx'
import { useCurrentUser } from '../../stores/currentUser.js'

const ROLE_COLORS = {
  viewer:   'bg-slate-100 text-slate-600',
  editor:   'bg-indigo-50 text-indigo-600',
  approver: 'bg-amber-50 text-amber-700',
  admin:    'bg-violet-50 text-violet-700',
  auditor:  'bg-teal-50 text-teal-700',
}

function RoleChip({ role }) {
  return (
    <span className={clsx(
      'px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide',
      ROLE_COLORS[role] ?? 'bg-slate-100 text-slate-600',
    )}>
      {role}
    </span>
  )
}

export default function UserSelector() {
  const { users, currentUser, setCurrentUser, loadUsers } = useCurrentUser()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (users.length === 0) loadUsers()
  }, [users.length, loadUsers])

  useEffect(() => {
    if (!open) return
    const onClick = (e) => {
      if (!ref.current?.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const initials = (currentUser?.display_name ?? 'OP')
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-slate-100 transition-colors"
        aria-label="Switch user"
      >
        <div className="w-7 h-7 rounded-full bg-indigo-100 border border-indigo-200 flex items-center justify-center">
          <span className="text-[11px] font-semibold text-indigo-700">{initials}</span>
        </div>
        <div className="hidden sm:block text-left">
          <div className="text-xs font-medium text-slate-700 leading-tight">
            {currentUser?.display_name ?? 'Select user'}
          </div>
          <div className="text-[10px] text-slate-500 leading-tight">
            {currentUser?.roles?.join(' · ') ?? 'demo mode'}
          </div>
        </div>
        <ChevronDown size={12} className="text-slate-400" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-72 bg-white rounded-lg border border-slate-200 shadow-lg py-1 z-50">
          <div className="px-3 py-2 border-b border-slate-100">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">
              Demo mode — pick a user
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              Edits, approvals, and freezes enforce by role.
            </div>
          </div>
          {users.map((u) => (
            <button
              key={u.id}
              onClick={() => { setCurrentUser(u.id); setOpen(false) }}
              className={clsx(
                'w-full text-left px-3 py-2 hover:bg-slate-50 flex items-start gap-2',
                u.id === currentUser?.id && 'bg-indigo-50/60',
              )}
            >
              <UserIcon size={13} className="text-slate-400 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-slate-800 truncate">{u.display_name}</span>
                  {u.id === currentUser?.id && <Check size={12} className="text-indigo-500" />}
                </div>
                <div className="text-[10px] text-slate-500 truncate">{u.email}</div>
                <div className="flex gap-1 mt-1 flex-wrap">
                  {u.roles.map((r) => <RoleChip key={r} role={r} />)}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
