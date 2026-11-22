import { useState } from 'react'
import { api, qs } from '../api'
import { Check, DataTable, Field, Modal, Page, useApp, useLoad } from '../components/ui'

export function PartyForm({ value, onChange, states, supplier }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value })
  return (
    <div className="form-grid">
      <Field label="Name" span={2}><input value={value.name} onChange={set('name')} autoFocus /></Field>
      {supplier && <Field label="Contact person"><input value={value.contact_person} onChange={set('contact_person')} /></Field>}
      <Field label="Phone"><input value={value.phone} onChange={set('phone')} /></Field>
      <Field label="Email"><input value={value.email} onChange={set('email')} /></Field>
      <Field label="GSTIN"><input value={value.gstin} maxLength={15} onChange={e => onChange({ ...value, gstin: e.target.value.toUpperCase(), state_code: e.target.value.length >= 2 ? e.target.value.slice(0, 2) : value.state_code })} /></Field>
      <Field label="State">
        <select value={value.state_code} onChange={e => onChange({ ...value, state_code: e.target.value, state: states.find(s => s.code === e.target.value)?.name || '' })}>
          <option value="">—</option>{states.map(s => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
        </select>
      </Field>
      {supplier && <Field label="Opening balance (payable) ₹"><input value={value.opening_balance} onChange={set('opening_balance')} inputMode="decimal" /></Field>}
      <Field label="Address" span={2}><input value={value.address} onChange={set('address')} /></Field>
      <Check label="Active" checked={value.is_active} onChange={v => onChange({ ...value, is_active: v })} />
    </div>
  )
}

export const blankParty = { name: '', phone: '', email: '', gstin: '', address: '', state: '', state_code: '', is_active: true, contact_person: '', opening_balance: 0 }

export default function Customers() {
  const { toast, user } = useApp()
  const [q, setQ] = useState('')
  const [edit, setEdit] = useState(null)
  const [hist, setHist] = useState(null)
  const states = useLoad(() => api.get('/api/states'), [])
  const { data, reload } = useLoad(() => api.get('/api/customers' + qs({ q })), [q])
  async function save() {
    try {
      const { id, created_at, contact_person, opening_balance, ...body } = edit
      id ? await api.put(`/api/customers/${id}`, body) : await api.post('/api/customers', body)
      toast('Customer saved'); setEdit(null); reload()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Page title="Customers" subtitle="Regular customers and B2B customers with GSTIN"
          actions={<button className="btn primary" onClick={() => setEdit({ ...blankParty })}>+ New customer</button>}>
      <div className="toolbar"><input placeholder="Search name / phone / GSTIN" value={q} onChange={e => setQ(e.target.value)} /></div>
      <DataTable rows={data} onRowClick={setHist} columns={[
        { key: 'name', label: 'Name' }, { key: 'phone', label: 'Phone' }, { key: 'gstin', label: 'GSTIN' },
        { key: 'state', label: 'State' }, { key: 'address', label: 'Address' },
        { key: 'act', label: '', render: r => user.role !== 'cashier' && <button className="btn small" onClick={e => { e.stopPropagation(); setEdit({ ...blankParty, ...r }) }}>Edit</button> }]} />
      {edit && <Modal title={edit.id ? 'Edit customer' : 'New customer'} onClose={() => setEdit(null)} footer={<button className="btn primary" onClick={save} disabled={!edit.name}>Save</button>}>
        <PartyForm value={edit} onChange={setEdit} states={states.data || []} />
      </Modal>}
      {hist && <CustomerBills c={hist} onClose={() => setHist(null)} />}
    </Page>
  )
}

function CustomerBills({ c, onClose }) {
  const { data } = useLoad(() => api.get(`/api/customers/${c.id}/bills`), [c.id])
  const total = (data || []).filter(b => b.status === 'ACTIVE').reduce((s, b) => s + b.grand_total, 0)
  return (
    <Modal wide title={`${c.name} — bills`} onClose={onClose}>
      <div className="muted">Total business: ₹{total.toFixed(2)}</div>
      <DataTable rows={data} columns={[{ key: 'bill_no', label: 'Bill' }, { key: 'bill_date', label: 'Date', type: 'datetime' },
        { key: 'grand_total', label: 'Total', type: 'money' }, { key: 'payment_mode', label: 'Paid' }, { key: 'status', label: 'Status' }]} />
    </Modal>
  )
}
