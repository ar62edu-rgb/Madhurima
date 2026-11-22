import { useState } from 'react'
import { api, qs } from '../api'
import { Badge, Card, DataTable, Field, Modal, Page, PeriodFilter, Select, Stat, Tabs, useApp, useLoad } from '../components/ui'
import { fmtDate, money, today } from '../utils'

export default function CashUpi() {
  const [tab, setTab] = useState('book')
  return (
    <Page title="Cash & UPI" subtitle="Daily cash book, other receipts / withdrawals and UPI register">
      <Tabs value={tab} onChange={setTab} tabs={[['book', 'Daily cash book'], ['entries', 'Cash in / out entries'], ['upi', 'UPI register']]} />
      {tab === 'book' && <CashBook />}
      {tab === 'entries' && <Entries />}
      {tab === 'upi' && <UpiRegister />}
    </Page>
  )
}

export function CashSummary({ s }) {
  return (
    <div className="cash-formula">
      <div><span>Opening cash</span><b>{money(s.opening_cash)}</b></div>
      <div className="plus"><span>+ Cash sales</span><b>{money(s.cash_sales)}</b></div>
      <div className="plus"><span>+ Other cash in</span><b>{money(s.other_cash_in)}</b></div>
      <div className="minus"><span>− Cash expenses</span><b>{money(s.cash_expenses)}</b></div>
      <div className="minus"><span>− Supplier payments (cash)</span><b>{money(s.cash_supplier_payments)}</b></div>
      <div className="minus"><span>− Cash refunds</span><b>{money(s.cash_refunds)}</b></div>
      <div className="minus"><span>− Other cash out</span><b>{money(s.other_cash_out)}</b></div>
      <div className="eq"><span>= Expected closing cash</span><b>{money(s.expected_cash)}</b></div>
    </div>
  )
}

function CashBook() {
  const [day, setDay] = useState(today())
  const { data } = useLoad(() => api.get('/api/cash-book' + qs({ day })), [day])
  const s = data?.summary
  return (
    <>
      <div className="toolbar"><Field label="Date"><input type="date" value={day} onChange={e => setDay(e.target.value)} /></Field>
        {s?.closing && <Badge tone={s.closing.status === 'CLOSED' ? 'green' : 'amber'}>Day {s.closing.status.toLowerCase()}</Badge>}</div>
      {s && <div className="grid2">
        <Card title="Cash position"><CashSummary s={s} />
          {s.closing && <div className="muted">Actual counted: {money(s.closing.actual_cash)} · Difference {money(s.closing.difference)}</div>}</Card>
        <Card title="UPI position">
          <div className="cash-formula">
            <div className="plus"><span>UPI sales</span><b>{money(s.upi_sales)}</b></div>
            <div className="plus"><span>Other UPI received</span><b>{money(s.upi_in_other)}</b></div>
            <div className="minus"><span>UPI expenses</span><b>{money(s.upi_expenses)}</b></div>
            <div className="minus"><span>UPI supplier payments</span><b>{money(s.upi_supplier_payments)}</b></div>
            <div className="minus"><span>UPI refunds / other out</span><b>{money(s.upi_refunds + s.upi_out_other)}</b></div>
            <div className="eq"><span>Net UPI for the day</span><b>{money(s.upi_net)}</b></div>
          </div>
          <div className="muted">Bills: {s.total_bills} · Cancelled: {s.cancelled_bills} · Total sales {money(s.total_sales)}</div>
        </Card>
      </div>}
      <h3>Cash transactions — {fmtDate(day)}</h3>
      <DataTable rows={data?.transactions} columns={[{ key: 'time', label: 'Time', render: r => r.time.slice(11, 16) }, { key: 'type', label: 'Type' },
        { key: 'ref', label: 'Reference' }, { key: 'in', label: 'Cash in', type: 'money' }, { key: 'out', label: 'Cash out', type: 'money' }, { key: 'balance', label: 'Balance', type: 'money' }]} />
    </>
  )
}

function Entries() {
  const { settings, toast, user } = useApp()
  const cats = (settings.cash_entry_categories || '').split(',').map(s => s.trim()).filter(Boolean)
  const [range, setRange] = useState([today(), today()])
  const [edit, setEdit] = useState(null)
  const { data, reload } = useLoad(() => api.get('/api/cash-entries' + qs({ from_date: range[0], to_date: range[1] })), [range[0], range[1]])
  const canEdit = user.role !== 'cashier'
  async function save() {
    try { await api.post('/api/cash-entries', { ...edit, amount: Number(edit.amount) }); toast('Entry saved'); setEdit(null); reload() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <>
      <div className="toolbar">
        <PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />
        {canEdit && <button className="btn primary" onClick={() => setEdit({ entry_date: today(), direction: 'IN', mode: 'CASH', category: cats[0] || '', amount: '', reference: '', remarks: '' })}>+ New entry</button>}
      </div>
      <DataTable rows={data} rowClass={r => r.is_cancelled ? 'cancelled' : ''} columns={[
        { key: 'entry_date', label: 'Date', type: 'date' }, { key: 'direction', label: 'In/Out', render: r => <Badge tone={r.direction === 'IN' ? 'green' : 'red'}>{r.direction}</Badge> },
        { key: 'mode', label: 'Mode' }, { key: 'category', label: 'Category' }, { key: 'amount', label: 'Amount', type: 'money' },
        { key: 'reference', label: 'Ref' }, { key: 'remarks', label: 'Remarks' }, { key: 'created_by', label: 'By' },
        { key: 'act', label: '', render: r => r.is_cancelled ? <Badge>Cancelled</Badge> : canEdit && <button className="btn small" onClick={async () => { if (confirm('Cancel entry?')) { try { await api.post(`/api/cash-entries/${r.id}/cancel`); reload() } catch (e) { toast(e.message, 'error') } } }}>Cancel</button> }]} />
      {edit && <Modal title="Cash / UPI entry" onClose={() => setEdit(null)} footer={<button className="btn primary" onClick={save} disabled={!(Number(edit.amount) > 0)}>Save</button>}>
        <div className="form-grid">
          <Field label="Date"><input type="date" value={edit.entry_date} onChange={e => setEdit({ ...edit, entry_date: e.target.value })} /></Field>
          <Field label="Direction"><Select value={edit.direction} onChange={v => setEdit({ ...edit, direction: v })} options={[['IN', 'Money in (receipt / addition)'], ['OUT', 'Money out (withdrawal / deposit)']]} /></Field>
          <Field label="Mode"><Select value={edit.mode} onChange={v => setEdit({ ...edit, mode: v })} options={[['CASH', 'Cash'], ['UPI', 'UPI']]} /></Field>
          <Field label="Category"><input list="cash-cats" value={edit.category} onChange={e => setEdit({ ...edit, category: e.target.value })} /><datalist id="cash-cats">{cats.map(c => <option key={c} value={c} />)}</datalist></Field>
          <Field label="Amount ₹"><input value={edit.amount} onChange={e => setEdit({ ...edit, amount: e.target.value })} inputMode="decimal" autoFocus /></Field>
          <Field label="Reference"><input value={edit.reference} onChange={e => setEdit({ ...edit, reference: e.target.value })} /></Field>
          <Field label="Remarks" span={2}><input value={edit.remarks} onChange={e => setEdit({ ...edit, remarks: e.target.value })} /></Field>
        </div>
      </Modal>}
    </>
  )
}

function UpiRegister() {
  const { toast } = useApp()
  const [range, setRange] = useState([today(), today()])
  const [dir, setDir] = useState('')
  const { data, reload } = useLoad(() => api.get('/api/upi-transactions' + qs({ from_date: range[0], to_date: range[1] })), [range[0], range[1]])
  const rows = (data?.rows || []).filter(r => !dir || r.direction === dir)
  async function verify(r) {
    try { await api.post(`/api/bills/${r.bill_id}/upi-verified?verified=${!r.verified}`); reload() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <>
      <div className="toolbar">
        <PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />
        <Select value={dir} onChange={setDir} placeholder="In & out" options={[['IN', 'Received'], ['OUT', 'Paid']]} />
      </div>
      {data && <div className="stats">
        <Stat label="UPI received" value={money(data.total_in)} tone="good" />
        <Stat label="UPI paid" value={money(data.total_out)} />
        <Stat label="Net UPI" value={money(data.net)} tone="accent" />
        <Stat label="Sales not yet verified" value={money(data.unverified_sales)} tone={data.unverified_sales ? 'warn' : ''} sub="Tick after checking your bank / UPI app" />
      </div>}
      <DataTable rows={rows} columns={[
        { key: 'date', label: 'Date', render: r => r.date.length > 10 ? `${fmtDate(r.date)} ${r.date.slice(11, 16)}` : fmtDate(r.date) },
        { key: 'direction', label: 'In/Out', render: r => <Badge tone={r.direction === 'IN' ? 'green' : 'red'}>{r.direction}</Badge> },
        { key: 'type', label: 'Type' }, { key: 'ref_no', label: 'Bill / Doc' }, { key: 'upi_ref', label: 'UPI Ref (UTR)' }, { key: 'party', label: 'Party' },
        { key: 'amount', label: 'Amount', type: 'money' },
        { key: 'verified', label: 'Verified', render: r => r.bill_id ? <input type="checkbox" checked={!!r.verified} onChange={() => verify(r)} /> : '' }]} />
    </>
  )
}
