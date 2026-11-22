import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { Badge, Card, DataTable, Field, Page, Stat, Tabs, useApp, useLoad } from '../components/ui'
import { fmtDate, money, today } from '../utils'
import { CashSummary } from './CashUpi'

const NOTES = [500, 200, 100, 50, 20, 10, 5, 2, 1]
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

export default function Closing() {
  const [tab, setTab] = useState('day')
  return (
    <Page title="Day / Month Closing" subtitle="Closing locks the period: no bills, expenses or entries can be added or changed until an admin reopens it">
      <Tabs value={tab} onChange={setTab} tabs={[['day', 'Daily closing'], ['month', 'Monthly closing']]} />
      {tab === 'day' ? <Daily /> : <Monthly />}
    </Page>
  )
}

function Daily() {
  const { user, toast } = useApp()
  const [day, setDay] = useState(today())
  const { data: s, reload } = useLoad(() => api.get('/api/daily-closing' + qs({ day })), [day])
  const list = useLoad(() => api.get('/api/daily-closings'), [])
  const [opening, setOpening] = useState('')
  const [actual, setActual] = useState('')
  const [denoms, setDenoms] = useState({})
  const [remarks, setRemarks] = useState('')

  useEffect(() => {
    if (!s) return
    setOpening(String(s.opening_cash))
    setActual(s.closing ? String(s.closing.actual_cash) : '')
    setRemarks(s.closing?.remarks || '')
    setDenoms({})
  }, [s])

  const denomTotal = NOTES.reduce((t, n) => t + n * (Number(denoms[n]) || 0), 0)
  const expected = s ? Math.round((Number(opening || 0) - s.opening_cash + s.expected_cash) * 100) / 100 : 0
  const diff = actual === '' ? null : Math.round((Number(actual) - expected) * 100) / 100
  const closed = s?.closing?.status === 'CLOSED'

  async function close() {
    if (!confirm(`Close ${fmtDate(day)}? Expected ${money(expected)}, counted ${money(actual)}.`)) return
    try {
      await api.post('/api/daily-closing', { closing_date: day, opening_cash: Number(opening) || 0, actual_cash: Number(actual) || 0, remarks })
      toast('Day closed and backup taken'); reload(); list.reload()
    } catch (e) { toast(e.message, 'error') }
  }
  async function reopen() {
    if (!confirm('Reopen this day? Entries will be allowed again.')) return
    try { await api.post(`/api/daily-closing/${day}/reopen`); toast('Day reopened'); reload(); list.reload() } catch (e) { toast(e.message, 'error') }
  }

  return (
    <>
      <div className="toolbar">
        <Field label="Closing date"><input type="date" value={day} max={today()} onChange={e => setDay(e.target.value)} /></Field>
        {s?.closing && <Badge tone={closed ? 'green' : 'amber'}>{closed ? `Closed by ${s.closing.closed_by}` : 'Reopened'}</Badge>}
      </div>
      {s && <>
        <div className="stats">
          <Stat label="Total sales" value={money(s.total_sales)} tone="accent" sub={`${s.total_bills} bills · ${s.cancelled_bills} cancelled`} />
          <Stat label="Cash sales" value={money(s.cash_sales)} />
          <Stat label="UPI sales" value={money(s.upi_sales)} />
          <Stat label="GST" value={money(s.total_tax)} />
          <Stat label="Net UPI" value={money(s.upi_net)} />
        </div>
        <div className="grid2">
          <Card title="Expected cash">
            <Field label={`Opening cash ${s.previous_closing_date ? `(carried forward from ${fmtDate(s.previous_closing_date)}: ${money(s.carried_forward_cash)})` : ''}`}>
              <input value={opening} onChange={e => setOpening(e.target.value)} disabled={closed} inputMode="decimal" />
            </Field>
            <CashSummary s={{ ...s, opening_cash: Number(opening) || 0, expected_cash: expected }} />
          </Card>
          <Card title="Physical cash count">
            <div className="denoms">
              {NOTES.map(n => (
                <label key={n}><span>₹{n} ×</span><input value={denoms[n] || ''} disabled={closed} inputMode="numeric"
                  onChange={e => setDenoms(d => ({ ...d, [n]: e.target.value }))} /><span className="muted">{money(n * (Number(denoms[n]) || 0))}</span></label>
              ))}
            </div>
            {denomTotal > 0 && !closed && <button className="btn small" onClick={() => setActual(String(denomTotal))}>Use counted total {money(denomTotal)}</button>}
            <Field label="Actual cash in drawer"><input value={actual} onChange={e => setActual(e.target.value)} disabled={closed} inputMode="decimal" /></Field>
            {diff !== null && <div className={`diff ${diff < 0 ? 'neg' : diff > 0 ? 'pos' : 'ok'}`}>
              Difference: {money(diff)} {diff === 0 ? '✓ tallied' : diff < 0 ? '(short)' : '(excess)'}</div>}
            <Field label="Closing remarks"><input value={remarks} onChange={e => setRemarks(e.target.value)} disabled={closed} /></Field>
            {!closed && <button className="btn primary" disabled={actual === ''} onClick={close}>Close day</button>}
            {closed && user.role === 'admin' && <button className="btn" onClick={reopen}>Reopen day</button>}
          </Card>
        </div>
      </>}
      <h3>Recent closings</h3>
      <DataTable rows={list.data} onRowClick={r => setDay(r.closing_date)} columns={[
        { key: 'closing_date', label: 'Date', type: 'date' }, { key: 'opening_cash', label: 'Opening', type: 'money' },
        { key: 'cash_sales', label: 'Cash sales', type: 'money' }, { key: 'expected_cash', label: 'Expected', type: 'money' },
        { key: 'actual_cash', label: 'Actual', type: 'money' }, { key: 'difference', label: 'Diff', type: 'money' },
        { key: 'total_sales', label: 'Total sales', type: 'money' }, { key: 'status', label: 'Status' }, { key: 'closed_by', label: 'By' }]} />
    </>
  )
}

function Monthly() {
  const { user, toast } = useApp()
  const now = new Date()
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  const [y, setY] = useState(prev.getFullYear())
  const [m, setM] = useState(prev.getMonth() + 1)
  const [remarks, setRemarks] = useState('')
  const { data: s, reload } = useLoad(() => api.get('/api/monthly-closing' + qs({ year: y, month: m })), [y, m])
  const list = useLoad(() => api.get('/api/monthly-closings'), [])
  const closed = s?.closing?.status === 'CLOSED'
  async function close() {
    try { await api.post('/api/monthly-closing', { year: y, month: m, remarks }); toast('Month closed'); reload(); list.reload() } catch (e) { toast(e.message, 'error') }
  }
  async function reopen() {
    try { await api.post(`/api/monthly-closing/${y}/${m}/reopen`); toast('Month reopened'); reload(); list.reload() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <>
      <div className="toolbar">
        <select value={m} onChange={e => setM(Number(e.target.value))}>{MONTHS.map((n, i) => <option key={n} value={i + 1}>{n}</option>)}</select>
        <input className="narrow" type="number" value={y} onChange={e => setY(Number(e.target.value))} />
        {s?.closing && <Badge tone={closed ? 'green' : 'amber'}>{closed ? 'Closed' : 'Reopened'}</Badge>}
      </div>
      {s && <>
        <div className="stats">
          <Stat label="Net sales" value={money(s.total_sales)} tone="accent" sub={`${s.total_bills} bills`} />
          <Stat label="Taxable sales" value={money(s.taxable_sales)} />
          <Stat label="Output GST" value={money(s.output_cgst + s.output_sgst + s.output_igst)} sub={`C ${money(s.output_cgst)} · S ${money(s.output_sgst)} · I ${money(s.output_igst)}`} />
          <Stat label="Purchases" value={money(s.purchases)} sub={`Input GST ${money(s.input_gst)}`} />
          <Stat label="Expenses" value={money(s.expenses)} />
          <Stat label="Cash / UPI" value={`${money(s.cash_sales)} / ${money(s.upi_sales)}`} />
          <Stat label="Cost of sales (est.)" value={money(s.cost_of_sales)} />
          <Stat label="Profit estimate" value={money(s.profit_estimate)} tone={s.profit_estimate < 0 ? 'bad' : 'good'} />
        </div>
        {s.unclosed_days.length > 0 && <div className="error-box">Days with bills not yet closed: {s.unclosed_days.map(fmtDate).join(', ')}</div>}
        {user.role === 'admin' && <div className="toolbar">
          {!closed && <><input placeholder="Remarks" value={remarks} onChange={e => setRemarks(e.target.value)} />
            <button className="btn primary" onClick={close}>Close {MONTHS[m - 1]} {y}</button></>}
          {closed && <button className="btn" onClick={reopen}>Reopen month</button>}
        </div>}
      </>}
      <h3>Closed months</h3>
      <DataTable rows={list.data} columns={[{ key: 'month', label: 'Month', render: r => `${MONTHS[r.month - 1]} ${r.year}` },
        { key: 'total_sales', label: 'Sales', type: 'money' }, { key: 'output_cgst', label: 'CGST', type: 'money' }, { key: 'output_sgst', label: 'SGST', type: 'money' },
        { key: 'purchases', label: 'Purchases', type: 'money' }, { key: 'expenses', label: 'Expenses', type: 'money' },
        { key: 'profit_estimate', label: 'Profit est.', type: 'money' }, { key: 'status', label: 'Status' }, { key: 'closed_by', label: 'By' }]} />
    </>
  )
}
