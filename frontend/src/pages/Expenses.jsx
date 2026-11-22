import { useState } from 'react'
import { api, qs } from '../api'
import { Badge, DataTable, Field, Modal, Page, PeriodFilter, Select, Stat, sumBy, useApp, useLoad } from '../components/ui'
import { money, presetRange, today } from '../utils'

export default function Expenses() {
  const { settings, toast, user } = useApp()
  const cats = (settings.expense_categories || '').split(',').map(s => s.trim()).filter(Boolean)
  const [range, setRange] = useState(presetRange('month'))
  const [cat, setCat] = useState('')
  const [edit, setEdit] = useState(null)
  const { data, reload } = useLoad(() => api.get('/api/expenses' + qs({ from_date: range[0], to_date: range[1], category: cat })), [range[0], range[1], cat])
  const active = (data || []).filter(e => !e.is_cancelled)
  async function save() {
    try { await api.post('/api/expenses', { ...edit, amount: Number(edit.amount) }); toast('Expense saved'); setEdit(null); reload() }
    catch (e) { toast(e.message, 'error') }
  }
  async function cancel(e) {
    if (!confirm(`Cancel expense of ${money(e.amount)}?`)) return
    try { await api.post(`/api/expenses/${e.id}/cancel`); reload() } catch (err) { toast(err.message, 'error') }
  }
  return (
    <Page title="Expenses" subtitle="Daily running expenses paid in cash or UPI"
          actions={<button className="btn primary" onClick={() => setEdit({ expense_date: today(), category: cats[0] || '', description: '', paid_to: '', amount: '', mode: 'CASH', reference: '' })}>+ New expense</button>}>
      <div className="toolbar">
        <PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />
        <Select value={cat} onChange={setCat} placeholder="All categories" options={cats} />
      </div>
      <div className="stats">
        <Stat label="Total" value={money(sumBy(active, 'amount'))} tone="accent" />
        <Stat label="Cash" value={money(sumBy(active.filter(e => e.mode === 'CASH'), 'amount'))} />
        <Stat label="UPI" value={money(sumBy(active.filter(e => e.mode === 'UPI'), 'amount'))} />
      </div>
      <DataTable rows={data} rowClass={r => r.is_cancelled ? 'cancelled' : ''} columns={[
        { key: 'expense_date', label: 'Date', type: 'date' }, { key: 'category', label: 'Category' }, { key: 'description', label: 'Description' },
        { key: 'paid_to', label: 'Paid to' }, { key: 'mode', label: 'Mode', render: r => <Badge tone={r.mode === 'CASH' ? 'green' : 'blue'}>{r.mode}</Badge> },
        { key: 'reference', label: 'Ref' }, { key: 'amount', label: 'Amount', type: 'money' }, { key: 'created_by', label: 'By' },
        { key: 'act', label: '', render: r => r.is_cancelled ? <Badge>Cancelled</Badge> : user.role !== 'cashier' && <button className="btn small" onClick={() => cancel(r)}>Cancel</button> },
      ]} />
      {edit && (
        <Modal title="New expense" onClose={() => setEdit(null)} footer={<button className="btn primary" onClick={save} disabled={!(Number(edit.amount) > 0) || !edit.category}>Save</button>}>
          <div className="form-grid">
            <Field label="Date"><input type="date" value={edit.expense_date} onChange={e => setEdit({ ...edit, expense_date: e.target.value })} /></Field>
            <Field label="Category"><input list="exp-cats" value={edit.category} onChange={e => setEdit({ ...edit, category: e.target.value })} />
              <datalist id="exp-cats">{cats.map(c => <option key={c} value={c} />)}</datalist></Field>
            <Field label="Amount ₹"><input value={edit.amount} onChange={e => setEdit({ ...edit, amount: e.target.value })} inputMode="decimal" autoFocus /></Field>
            <Field label="Mode"><Select value={edit.mode} onChange={v => setEdit({ ...edit, mode: v })} options={[['CASH', 'Cash'], ['UPI', 'UPI']]} /></Field>
            <Field label="Paid to"><input value={edit.paid_to} onChange={e => setEdit({ ...edit, paid_to: e.target.value })} /></Field>
            <Field label="Reference"><input value={edit.reference} onChange={e => setEdit({ ...edit, reference: e.target.value })} /></Field>
            <Field label="Description" span={2}><input value={edit.description} onChange={e => setEdit({ ...edit, description: e.target.value })} /></Field>
          </div>
        </Modal>
      )}
    </Page>
  )
}
