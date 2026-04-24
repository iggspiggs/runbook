import React, { useEffect, useRef, useState } from 'react'
import { Info, X } from 'lucide-react'
import clsx from 'clsx'

export default function PageInfo({ title, summary, bullets = [] }) {
  const [open, setOpen] = useState(false)
  const popRef = useRef(null)
  const btnRef = useRef(null)

  useEffect(() => {
    if (!open) return

    const onClick = (e) => {
      if (popRef.current?.contains(e.target)) return
      if (btnRef.current?.contains(e.target)) return
      setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative inline-flex items-center">
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          'ml-1.5 flex items-center justify-center w-5 h-5 rounded-full',
          'text-slate-400 hover:text-indigo-500 hover:bg-indigo-50',
          'transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-200'
        )}
        aria-label={`About ${title}`}
        aria-expanded={open}
      >
        <Info size={13} />
      </button>

      {open && (
        <div
          ref={popRef}
          role="dialog"
          className="
            absolute left-0 top-full mt-2 z-50 w-80
            rounded-lg border border-slate-200 bg-white shadow-lg
            p-4
          "
        >
          <div className="flex items-start justify-between gap-2 mb-2">
            <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="p-1 -m-1 rounded text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              aria-label="Close"
            >
              <X size={14} />
            </button>
          </div>
          {summary && <p className="text-xs text-slate-600 leading-relaxed">{summary}</p>}
          {bullets.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {bullets.map((b, i) => (
                <li key={i} className="text-xs text-slate-600 flex gap-2">
                  <span className="text-indigo-400 mt-1">•</span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
