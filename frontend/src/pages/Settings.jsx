import { useEffect, useState } from 'react'
import { api, qs, setToken } from '../api'
import { Check, DataTable, Field, Modal, Page, Select, Tabs, useApp, useLoad } from '../components/ui'

export default function Settings() {
  const [tab, setTab] = useState('restaurant')
  return (
    <Page title="Settings">
      <Tabs value={tab} onChange={setTab} tabs={[['restaurant', 'Restaurant & GST'], ['billing', 'Billing & printing'], ['users', 'Users & permissions'], ['tables', 'Tables'], ['account', 'My password'], ['audit', 'Audit log']]} />
      {tab === 'restaurant' && <SettingsForm fields={RESTAURANT} />}
      {tab === 'billing' && <SettingsForm fields={BILLING} />}
      {tab === 'users' && <Users />}
      {tab === 'tables' && <Tables />}
      {tab === 'account' && <Password />}
      {tab === 'audit' && <Audit />}
    </Page>
  )
}

const RESTAURANT = [
  ['restaurant_name', 'Restaurant name'], ['address', 'Address'], ['city', 'City'], ['pincode', 'PIN code'], ['phone', 'Phone'], ['email', 'Email'],
  ['gstin', 'GSTIN', 'State code is taken from the first 2 digits'], ['fssai', 'FSSAI licence number'],
  ['state', 'State', null, 'state'], ['state_code', 'State code'],
  ['gst_registration_type', 'GST registration type', 'Composition / unregistered prints a Bill of Supply without GST', [['REGULAR', 'Regular'], ['COMPOSITION', 'Composition'], ['UNREGISTERED', 'Unregistered']]],
  ['default_gst_rate', 'Default GST rate % for new items', null, ['0', '5', '12', '18', '28'].map(x => [x, x + '%'])],
  ['default_hsn', 'Default HSN / SAC'],
  ['prices_include_gst', 'Menu prices', null, [['false', 'Exclusive — GST added on bill'], ['true', 'Inclusive — GST included in price']]],
]
const BILLING = [
  ['bill_prefix', 'Invoice series prefix', 'Bills are numbered PREFIX/YY-YY/00001, restarting each financial year'],
  ['purchase_prefix', 'Purchase number prefix'], ['credit_note_prefix', 'Credit note prefix'], ['debit_note_prefix', 'Debit note prefix'],
  ['invoice_title', 'Invoice title'], ['invoice_footer', 'Invoice footer message'],
  ['print_format', 'Default bill printer', null, [['80', 'Thermal 80 mm'], ['58', 'Thermal 58 mm'], ['A4', 'A4 sheet']]],
  ['print_copies', 'Copies per bill', null, [['1', '1'], ['2', '2'], ['0', 'Do not print automatically']]],
  ['show_upi_qr_text', 'UPI ID to show on bill (optional)'],
  ['round_off', 'Round bill to nearest rupee', null, 'bool'], ['allow_negative_stock', 'Allow billing when stock is insufficient', null, 'bool'],
  ['recipe_stock_deduction', 'Deduct recipe ingredients on sale', null, 'bool'], ['lock_after_daily_closing', 'Lock entries after daily closing', null, 'bool'],
  ['expense_categories', 'Expense categories (comma separated)'], ['cash_entry_categories', 'Cash in/out categories (comma separated)'],
]

function SettingsForm({ fields }) {
  const { settings, reloadSettings, toast } = useApp()
  const [f, setF] = useState(settings)
  const states = useLoad(() => api.get('/api/states'), [])
  async function save() {
    const body = Object.fromEntries(fields.map(([k]) => [k, f[k] ?? '']))
    try { await api.put('/api/settings', body); await reloadSettings(); toast('Settings saved') } catch (e) { toast(e.message, 'error') }
  }
  return (
    <div className="card">
      <div className="form-grid">
        {fields.map(([k, label, hint, opt]) => (
          <Field key={k} label={label} hint={hint}>
            {opt === 'bool' ? <Check label="Yes" checked={f[k] === 'true'} onChange={v => setF({ ...f, [k]: v ? 'true' : 'false' })} />
              : opt === 'state' ? <select value={f.state_code} onChange={e => setF({ ...f, state_code: e.target.value, state: (states.data || []).find(s => s.code === e.target.value)?.name || '' })}>
                  {(states.data || []).map(s => <option key={s.code} value={s.code}>{s.name}</option>)}</select>
              : Array.isArray(opt) ? <Select value={f[k]} onChange={v => setF({ ...f, [k]: v })} options={opt} />
              : <input value={f[k] ?? ''} onChange={e => setF({ ...f, [k]: e.target.value })} disabled={k === 'state_code'} />}
          </Field>
        ))}
      </div>
      <button className="btn primary" onClick={save}>Save settings</button>
    </div>
  )
}

function Users() {
  const { toast } = useApp()
  const { data, reload } = useLoad(() => api.get('/api/users'), [])
  const [edit, setEdit] = useState(null)
  async function save() {
    try { edit.id ? await api.put(`/api/users/${edit.id}`, edit) : await api.post('/api/users', edit); toast('User saved'); setEdit(null); reload() }
    catch (e) { toast(e.message, 'error') }
  }
  return (
    <>
      <div className="toolbar"><button className="btn primary" onClick={() => setEdit({ username: '', full_name: '', password: '', role: 'cashier', can_edit_price: false, can_discount: true, can_cancel_bill: false, is_active: true })}>+ New user</button></div>
      <DataTable rows={data} onRowClick={r => setEdit({ ...r, password: '' })} columns={[
        { key: 'username', label: 'Username' }, { key: 'full_name', label: 'Name' }, { key: 'role', label: 'Role' },
        { key: 'can_edit_price', label: 'Change price' }, { key: 'can_discount', label: 'Discount' }, { key: 'can_cancel_bill', label: 'Cancel bills' }, { key: 'is_active', label: 'Active' }]} />
      <p className="muted small">Admin: everything. Manager: all modules except settings, users and backup. Cashier: POS, bills, expenses, cash view and customers.</p>
      {edit && <Modal title={edit.id ? `Edit ${edit.username}` : 'New user'} onClose={() => setEdit(null)} footer={<button className="btn primary" onClick={save}>Save</button>}>
        <div className="form-grid">
          <Field label="Username"><input value={edit.username} disabled={!!edit.id} onChange={e => setEdit({ ...edit, username: e.target.value })} /></Field>
          <Field label="Full name"><input value={edit.full_name} onChange={e => setEdit({ ...edit, full_name: e.target.value })} /></Field>
          <Field label={edit.id ? 'New password (leave blank to keep)' : 'Password (min 6)'}><input type="password" value={edit.password} onChange={e => setEdit({ ...edit, password: e.target.value })} autoComplete="new-password" /></Field>
          <Field label="Role"><Select value={edit.role} onChange={v => setEdit({ ...edit, role: v })} options={[['cashier', 'Cashier'], ['manager', 'Manager'], ['admin', 'Admin']]} /></Field>
        </div>
        <Check label="Can change item price in POS" checked={edit.can_edit_price} onChange={v => setEdit({ ...edit, can_edit_price: v })} />
        <Check label="Can give discounts" checked={edit.can_discount} onChange={v => setEdit({ ...edit, can_discount: v })} />
        <Check label="Can cancel bills" checked={edit.can_cancel_bill} onChange={v => setEdit({ ...edit, can_cancel_bill: v })} />
        <Check label="Active" checked={edit.is_active} onChange={v => setEdit({ ...edit, is_active: v })} />
      </Modal>}
    </>
  )
}

function Tables() {
  const { toast } = useApp()
  const { data, reload } = useLoad(() => api.get('/api/tables'), [])
  const [edit, setEdit] = useState(null)
  async function save() {
    try { const b = { ...edit, seats: Number(edit.seats) || 0 }; edit.id ? await api.put(`/api/tables/${edit.id}`, b) : await api.post('/api/tables', b); setEdit(null); reload() }
    catch (e) { toast(e.message, 'error') }
  }
  return (
    <>
      <div className="toolbar"><button className="btn primary" onClick={() => setEdit({ name: '', area: 'Main Hall', seats: 4, is_active: true })}>+ New table</button></div>
      <DataTable rows={data} onRowClick={setEdit} columns={[{ key: 'name', label: 'Table' }, { key: 'area', label: 'Area' }, { key: 'seats', label: 'Seats', type: 'num' }, { key: 'is_active', label: 'Active' }]} />
      {edit && <Modal title="Table" onClose={() => setEdit(null)} footer={<button className="btn primary" onClick={save}>Save</button>}>
        <Field label="Name"><input value={edit.name} onChange={e => setEdit({ ...edit, name: e.target.value })} autoFocus /></Field>
        <Field label="Area"><input value={edit.area} onChange={e => setEdit({ ...edit, area: e.target.value })} /></Field>
        <Field label="Seats"><input value={edit.seats} onChange={e => setEdit({ ...edit, seats: e.target.value })} /></Field>
        <Check label="Active" checked={edit.is_active} onChange={v => setEdit({ ...edit, is_active: v })} />
      </Modal>}
    </>
  )
}

function Password() {
  const { toast } = useApp()
  const [f, setF] = useState({ current_password: '', new_password: '', confirm: '' })
  async function save() {
    if (f.new_password !== f.confirm) return toast('Passwords do not match', 'error')
    try {
      const r = await api.post('/api/auth/change-password', f)
      setToken(r.token)
      toast('Password changed'); setF({ current_password: '', new_password: '', confirm: '' })
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <div className="card narrow-card">
      <Field label="Current password"><input type="password" value={f.current_password} onChange={e => setF({ ...f, current_password: e.target.value })} /></Field>
      <Field label="New password"><input type="password" value={f.new_password} onChange={e => setF({ ...f, new_password: e.target.value })} autoComplete="new-password" /></Field>
      <Field label="Confirm"><input type="password" value={f.confirm} onChange={e => setF({ ...f, confirm: e.target.value })} autoComplete="new-password" /></Field>
      <button className="btn primary" onClick={save}>Change password</button>
    </div>
  )
}

function Audit() {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  useEffect(() => { const t = setTimeout(() => setDebounced(q), 300); return () => clearTimeout(t) }, [q])
  const { data } = useLoad(() => api.get('/api/audit-logs' + qs({ q: debounced })), [debounced])
  return (
    <>
      <div className="toolbar"><input placeholder="Filter by action / user / reference" value={q} onChange={e => setQ(e.target.value)} /></div>
      <DataTable rows={data} maxHeight="65vh" columns={[{ key: 'at', label: 'Time', type: 'datetime' }, { key: 'username', label: 'User' }, { key: 'action', label: 'Action' },
        { key: 'entity', label: 'Entity' }, { key: 'entity_id', label: 'Ref' }, { key: 'details', label: 'Details', render: r => <span className="small mono">{String(r.details).slice(0, 160)}</span> }]} />
    </>
  )
}
