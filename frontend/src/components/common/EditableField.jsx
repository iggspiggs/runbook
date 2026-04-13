import React, { useState, useRef, useCallback } from 'react'
import { Edit2, Check, X, Wand2, AlertCircle, HelpCircle, Plus, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { simulateChange } from '../../api/client.js'

// Usage:
//   <EditableField
//     ruleId="RULE-001"
//     field={{
//       key: 'threshold',
//       label: 'Alert Threshold',
//       field_type: 'number',
//       current_value: 100,
//       default_value: 50,
//       description: 'Triggers alert when exceeded',
//       validation: { min: 0, max: 1000 },
//     }}
//     onSave={(key, value) => Promise<void>}
//   />

// ---------------------------------------------------------------------------
// Sub-renderers for each field_type
// ---------------------------------------------------------------------------

function StringInput({ value, onChange }) {
  return (
    <input
      type="text"
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      className="
        w-full px-2.5 py-1.5 rounded-md text-sm
        border border-slate-300 bg-white text-slate-900
        focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
      "
    />
  )
}

function NumberInput({ value, onChange, validation = {} }) {
  const { min, max, step = 1 } = validation
  return (
    <input
      type="number"
      value={value ?? ''}
      min={min}
      max={max}
      step={step}
      onChange={e => onChange(e.target.valueAsNumber)}
      className="
        w-full px-2.5 py-1.5 rounded-md text-sm
        border border-slate-300 bg-white text-slate-900
        focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
      "
    />
  )
}

function BooleanToggle({ value, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!!value}
      onClick={() => onChange(!value)}
      className={clsx(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
        value ? 'bg-indigo-500' : 'bg-slate-200'
      )}
    >
      <span
        className={clsx(
          'inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform',
          value ? 'translate-x-[18px]' : 'translate-x-0.5'
        )}
      />
    </button>
  )
}

function SelectInput({ value, onChange, validation = {} }) {
  const options = validation.options ?? []
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      className="
        w-full px-2.5 py-1.5 rounded-md text-sm
        border border-slate-300 bg-white text-slate-900
        focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
      "
    >
      <option value="">Select…</option>
      {options.map(opt => (
        <option key={opt} value={opt}>{opt}</option>
      ))}
    </select>
  )
}

function ListInput({ value, onChange }) {
  const [draft, setDraft] = useState('')
  const items = Array.isArray(value) ? value : []

  const addItem = () => {
    const trimmed = draft.trim()
    if (trimmed && !items.includes(trimmed)) {
      onChange([...items, trimmed])
    }
    setDraft('')
  }

  const removeItem = (idx) => {
    onChange(items.filter((_, i) => i !== idx))
  }

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1">
        {items.map((item, idx) => (
          <span
            key={idx}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-medium"
          >
            {item}
            <button
              type="button"
              onClick={() => removeItem(idx)}
              aria-label={`Remove ${item}`}
              className="hover:text-indigo-900"
            >
              <X size={11} />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input
          type="text"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addItem())}
          placeholder="Add item…"
          className="
            flex-1 px-2.5 py-1.5 rounded-md text-sm
            border border-slate-300 bg-white text-slate-900
            focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
          "
        />
        <button
          type="button"
          onClick={addItem}
          className="px-2 py-1.5 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors"
          aria-label="Add item"
        >
          <Plus size={14} />
        </button>
      </div>
    </div>
  )
}

function JsonInput({ value, onChange, onError }) {
  const [raw, setRaw] = useState(
    typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  )

  const handleChange = (text) => {
    setRaw(text)
    try {
      const parsed = JSON.parse(text)
      onChange(parsed)
      onError(null)
    } catch {
      onError('Invalid JSON')
    }
  }

  return (
    <textarea
      value={raw}
      onChange={e => handleChange(e.target.value)}
      rows={5}
      spellCheck={false}
      className="
        w-full px-2.5 py-1.5 rounded-md text-xs font-mono
        border border-slate-300 bg-slate-50 text-slate-900
        focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500
        resize-y
      "
    />
  )
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function validateField(value, field) {
  const { field_type, validation = {}, required } = field

  if (required && (value === null || value === undefined || value === '')) {
    return 'This field is required'
  }

  if (field_type === 'number') {
    if (validation.min !== undefined && value < validation.min) {
      return `Minimum value is ${validation.min}`
    }
    if (validation.max !== undefined && value > validation.max) {
      return `Maximum value is ${validation.max}`
    }
  }

  if (field_type === 'string' && validation.max_length && String(value).length > validation.max_length) {
    return `Maximum ${validation.max_length} characters`
  }

  if (field_type === 'string' && validation.pattern) {
    const re = new RegExp(validation.pattern)
    if (!re.test(String(value))) {
      return `Must match pattern: ${validation.pattern}`
    }
  }

  return null
}

// ---------------------------------------------------------------------------
// Main EditableField component
// ---------------------------------------------------------------------------

/**
 * EditableField — inline editor for a single editable rule field.
 *
 * @param {Object} props
 * @param {string} props.ruleId - parent rule ID (for simulation calls)
 * @param {Object} props.field - field descriptor from rule.editable[]
 * @param {function} props.onSave - async (key, value) => void
 * @param {boolean} [props.readOnly=false]
 */
export default function EditableField({ ruleId, field, onSave, readOnly = false }) {
  const {
    key,
    label,
    field_type,
    current_value,
    default_value,
    description,
    validation = {},
    unit,
  } = field

  const [editing, setEditing]       = useState(false)
  const [draftValue, setDraftValue] = useState(current_value)
  const [error, setError]           = useState(null)
  const [saving, setSaving]         = useState(false)
  const [simulating, setSimulating] = useState(false)
  const [simResult, setSimResult]   = useState(null)
  const prevValueRef                = useRef(current_value)

  const startEdit = () => {
    setDraftValue(current_value)
    setError(null)
    setSimResult(null)
    setEditing(true)
  }

  const cancelEdit = () => {
    setEditing(false)
    setDraftValue(current_value)
    setError(null)
    setSimResult(null)
  }

  const handleSave = async () => {
    const err = validateField(draftValue, field)
    if (err) {
      setError(err)
      return
    }

    setSaving(true)
    try {
      await onSave(key, draftValue)
      prevValueRef.current = draftValue
      setEditing(false)
      setSimResult(null)
    } catch (e) {
      setError(e.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleWhatIf = async () => {
    const err = validateField(draftValue, field)
    if (err) {
      setError(err)
      return
    }

    setSimulating(true)
    setSimResult(null)
    try {
      const result = await simulateChange(ruleId, { [key]: draftValue })
      setSimResult(result)
    } catch (e) {
      setError(`Simulation failed: ${e.message}`)
    } finally {
      setSimulating(false)
    }
  }

  // Render the appropriate input widget
  const renderInput = () => {
    const props = { value: draftValue, onChange: setDraftValue, validation }

    switch (field_type) {
      case 'number':  return <NumberInput  {...props} />
      case 'boolean': return <BooleanToggle {...props} />
      case 'select':  return <SelectInput  {...props} />
      case 'list':    return <ListInput    {...props} />
      case 'json':    return <JsonInput    {...props} onError={setError} />
      default:        return <StringInput  {...props} />
    }
  }

  // Render the current value in read-only display mode
  const renderDisplayValue = () => {
    const v = current_value
    if (v === null || v === undefined) {
      return <span className="text-slate-400 italic text-sm">Not set</span>
    }
    if (field_type === 'boolean') {
      return (
        <span className={clsx(
          'text-sm font-medium',
          v ? 'text-green-600' : 'text-slate-500'
        )}>
          {v ? 'Enabled' : 'Disabled'}
        </span>
      )
    }
    if (field_type === 'list') {
      const items = Array.isArray(v) ? v : []
      return (
        <div className="flex flex-wrap gap-1 mt-0.5">
          {items.length === 0
            ? <span className="text-slate-400 italic text-sm">Empty</span>
            : items.map((item, i) => (
                <span key={i} className="chip">{item}</span>
              ))
          }
        </div>
      )
    }
    if (field_type === 'json') {
      return (
        <pre className="text-xs font-mono bg-slate-50 border border-slate-200 rounded-md p-2 overflow-auto max-h-24 text-slate-700">
          {JSON.stringify(v, null, 2)}
        </pre>
      )
    }
    return (
      <span className="text-sm text-slate-900">
        {String(v)}{unit && <span className="text-slate-500 ml-1">{unit}</span>}
      </span>
    )
  }

  return (
    <div className={clsx(
      'rounded-lg border bg-white p-3 space-y-1.5',
      editing ? 'border-indigo-300 shadow-sm' : 'border-slate-200'
    )}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-slate-700">{label}</span>
            <code className="text-xs text-slate-400 font-mono">{key}</code>
            {description && (
              <span title={description} className="text-slate-400 cursor-help">
                <HelpCircle size={12} />
              </span>
            )}
          </div>
          {description && (
            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{description}</p>
          )}
        </div>

        {!readOnly && !editing && (
          <button
            onClick={startEdit}
            className="flex-shrink-0 p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
            aria-label={`Edit ${label}`}
          >
            <Edit2 size={13} />
          </button>
        )}
      </div>

      {/* Value display / edit area */}
      {editing ? (
        <div className="space-y-2">
          {renderInput()}

          {/* Error */}
          {error && (
            <div className="flex items-center gap-1.5 text-xs text-red-600">
              <AlertCircle size={12} />
              {error}
            </div>
          )}

          {/* Simulation result */}
          {simResult && (
            <div className="rounded-md bg-amber-50 border border-amber-200 p-2 space-y-1">
              <p className="text-xs font-semibold text-amber-800">What-if preview</p>
              {simResult.warnings?.map((w, i) => (
                <p key={i} className="text-xs text-amber-700">• {w}</p>
              ))}
              {simResult.affected_rules?.length > 0 && (
                <p className="text-xs text-amber-700">
                  Affects {simResult.affected_rules.length} downstream rule(s)
                </p>
              )}
              {simResult.summary && (
                <p className="text-xs text-amber-700">{simResult.summary}</p>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-1.5 pt-0.5">
            <button
              onClick={handleSave}
              disabled={saving}
              className="
                flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium
                bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50
                transition-colors
              "
            >
              {saving ? (
                <span className="animate-spin">↻</span>
              ) : (
                <Check size={12} />
              )}
              Save
            </button>

            <button
              onClick={handleWhatIf}
              disabled={simulating}
              className="
                flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium
                bg-amber-50 text-amber-700 border border-amber-200
                hover:bg-amber-100 disabled:opacity-50 transition-colors
              "
            >
              {simulating ? (
                <span className="animate-spin">↻</span>
              ) : (
                <Wand2 size={12} />
              )}
              What-if
            </button>

            <button
              onClick={cancelEdit}
              className="
                flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium
                text-slate-600 hover:bg-slate-100 transition-colors
              "
            >
              <X size={12} />
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-1">
          {renderDisplayValue()}
          {default_value !== undefined && default_value !== null && (
            <p className="text-xs text-slate-400">
              Default: <span className="font-mono">{String(default_value)}</span>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
