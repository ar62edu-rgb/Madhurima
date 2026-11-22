import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { PRESETS, presetRange, money, qty, fmtDate } from '../utils'

/* ---------------- app context: user, settings, toast ---------------- */
export const AppCtx = createContext(null)
export const useApp = () => useContext(AppCtx)

export function ToastHost({ toasts }) {
  return (
    <div className="toasts">
      {toasts.map(t => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
    </div>
  )
}

export function useToasts() {
  const [toasts, setToasts] = useState([])
  const push = useCallback((msg, kind = 'ok') => {
    const id = Math.random()
    setToasts(t => [...t, { id, msg, kind }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), kind === 'error' ? 6000 : 3000)
  }, [])
  return [toasts, push]
}

/* ---------------- data loading hook ---------------- */
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const reload = useCallback(async () => {
    const my = ++seq.current
    setLoading(true)
    try {
      const d = await fn()
      if (my === seq.current) { setData(d); setError(null) }
    } catch (e) {
      if (my === seq.current) setError(e.message)
    } finally {
      if (my === seq.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { reload() }, [reload])
  return { data, error, loading, reload, setData }
}

/* ---------------- layout bits ---------------- */
export function Page({ title, actions, children, subtitle }) {
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          {subtitle && <div className="muted">{subtitle}</div>}
        </div>
        <div className="row gap">{actions}</div>
      </div>
      {children}
    </div>
  )
}

export function Card({ title, children, actions, className = '' }) {
  return (
    <div className={`card ${className}`}>
      {(title || actions) && <div className="card-head"><h3>{title}</h3><div className="row gap">{actions}</div></div>}
      {children}
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs">
      {tabs.map(([k, label]) => (
        <button key={k} className={value === k ? 'active' : ''} onClick={() => onChange(k)}>{label}</button>
      ))}
    </div>
  )
}

export function Stat({ label, value, sub, tone }) {
  return (
    <div className={`stat ${tone || ''}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export function Badge({ children, tone = 'grey' }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export function Loading() { return <div className="muted pad">Loading…</div> }
export function ErrorBox({ error }) { return error ? <div className="error-box">{error}</div> : null }
export function Empty({ children = 'Nothing to show' }) { return <div className="empty">{children}</div> }

/* ---------------- modal ---------------- */
export function Modal({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className={`modal ${wide ? 'wide' : ''}`}>
        <div className="modal-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose}>✕</button></div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  )
}

/* ---------------- form fields ---------------- */
export function Field({ label, children, hint, span }) {
  return (
    <label className={`field ${span ? 'span-' + span : ''}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  )
}

export function Input({ value, onChange, type = 'text', ...rest }) {
  return <input type={type} value={value ?? ''} onChange={e => onChange(type === 'number' ? e.target.value : e.target.value)} {...rest} />
}

export function Select({ value, onChange, options, placeholder, ...rest }) {
  return (
    <select value={value ?? ''} onChange={e => onChange(e.target.value)} {...rest}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map(o => Array.isArray(o)
        ? <option key={o[0]} value={o[0]}>{o[1]}</option>
        : <option key={o} value={o}>{o}</option>)}
    </select>
  )
}

export function Check({ label, checked, onChange }) {
  return (
    <label className="check">
      <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} /> {label}
    </label>
  )
}

/* ---------------- period filter ---------------- */
export function PeriodFilter({ from, to, onChange, extra }) {
  const [preset, setPreset] = useState('')
  return (
    <div className="period">
      <select value={preset} onChange={e => { setPreset(e.target.value); if (e.target.value) onChange(...presetRange(e.target.value)) }}>
        <option value="">Custom</option>
        {PRESETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <input type="date" value={from} onChange={e => { setPreset(''); onChange(e.target.value, to) }} />
      <span className="muted">to</span>
      <input type="date" value={to} onChange={e => { setPreset(''); onChange(from, e.target.value) }} />
      {extra}
    </div>
  )
}

/* ---------------- data table ---------------- */
// columns: [{key,label,type:'money'|'num'|'date'|'datetime'|'text'|'pct', render?:(row)=>node, total?:bool}]
export function DataTable({ columns, rows, totals, onRowClick, empty, maxHeight, rowClass }) {
  const [sort, setSort] = useState(null)
  const sorted = useMemo(() => {
    if (!sort || !rows) return rows || []
    const { key, dir } = sort
    return [...rows].sort((a, b) => {
      const x = a[key], y = b[key]
      if (typeof x === 'number' && typeof y === 'number') return dir * (x - y)
      return dir * String(x ?? '').localeCompare(String(y ?? ''))
    })
  }, [rows, sort])
  if (!rows?.length) return <Empty>{empty || 'No records'}</Empty>
  const cell = (c, r) => {
    if (c.render) return c.render(r)
    const v = r[c.key]
    if (c.type === 'money') return money(v)
    if (c.type === 'num') return typeof v === 'number' ? qty(v) : v
    if (c.type === 'pct') return v === '' || v == null ? '' : `${v}%`
    if (c.type === 'date' && typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v)) return fmtDate(v)
    if (c.type === 'datetime' && v) return `${fmtDate(v)} ${String(v).slice(11, 16)}`
    if (typeof v === 'boolean') return v ? 'Yes' : 'No'
    return v
  }
  const numeric = (c) => ['money', 'num', 'pct'].includes(c.type)
  return (
    <div className="table-wrap" style={maxHeight ? { maxHeight } : undefined}>
      <table className="table">
        <thead>
          <tr>
            {columns.map(c => (
              <th key={c.key} className={numeric(c) ? 'r' : ''}
                  onClick={() => !c.render && setSort(s => ({ key: c.key, dir: s?.key === c.key ? -s.dir : 1 }))}>
                {c.label}{sort?.key === c.key ? (sort.dir > 0 ? ' ▲' : ' ▼') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={r.id ?? i} onClick={onRowClick ? () => onRowClick(r) : undefined}
                className={`${onRowClick ? 'clickable' : ''} ${rowClass ? rowClass(r) : ''}`}>
              {columns.map(c => <td key={c.key} className={numeric(c) ? 'r' : ''}>{cell(c, r)}</td>)}
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr>
              {columns.map((c, i) => (
                <td key={c.key} className={numeric(c) ? 'r' : ''}>
                  {i === 0 ? 'Total' : totals[c.key] !== undefined ? (c.type === 'money' ? money(totals[c.key]) : qty(totals[c.key])) : ''}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

export function sumBy(rows, key) {
  return Math.round((rows || []).reduce((s, r) => s + (Number(r[key]) || 0), 0) * 100) / 100
}

/* ---------------- confirm with reason ---------------- */
export function ReasonDialog({ title, label = 'Reason', confirmText = 'Confirm', onCancel, onConfirm, danger = true }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <Modal title={title} onClose={onCancel} footer={<>
      <button className="btn" onClick={onCancel}>Back</button>
      <button className={`btn ${danger ? 'danger' : 'primary'}`} disabled={reason.trim().length < 3 || busy}
              onClick={async () => { setBusy(true); try { await onConfirm(reason) } finally { setBusy(false) } }}>{confirmText}</button>
    </>}>
      <Field label={label}><textarea rows={3} value={reason} onChange={e => setReason(e.target.value)} autoFocus /></Field>
    </Modal>
  )
}
