import { useState } from 'react'
import { api } from '../api'
import { Badge, DataTable, Modal, Page, Stat, sumBy, useApp, useLoad } from '../components/ui'
import { money } from '../utils'
import { blankParty, PartyForm } from './Customers'
import { PaymentDialog } from './Purchases'

export default function Suppliers() {
  const { toast } = useApp()
  const [edit, setEdit] = useState(null)
  const [ledger, setLedger] = useState(null)
  const states = useLoad(() => api.get('/api/states'), [])
  const { data, reload } = useLoad(() => api.get('/api/suppliers'), [])
  async function save() {
    try {
      const { id, created_at, purchases, paid, returns, outstanding, ...body } = edit
      body.opening_balance = Number(body.opening_balance) || 0
      id ? await api.put(`/api/suppliers/${id}`, body) : await api.post('/api/suppliers', body)
      toast('Supplier saved'); setEdit(null); reload()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Page title="Suppliers" subtitle="Supplier master, ledger, outstanding and payments"
          actions={<button className="btn primary" onClick={() => setEdit({ ...blankParty })}>+ New supplier</button>}>
      <div className="stats">
        <Stat label="Suppliers" value={(data || []).length} />
        <Stat label="Total outstanding" value={money(sumBy((data || []).filter(s => s.outstanding > 0), 'outstanding'))} tone="warn" />
      </div>
      <DataTable rows={data} onRowClick={setLedger} columns={[
        { key: 'name', label: 'Supplier' }, { key: 'phone', label: 'Phone' }, { key: 'gstin', label: 'GSTIN' }, { key: 'state', label: 'State' },
        { key: 'purchases', label: 'Purchases', type: 'money' }, { key: 'paid', label: 'Paid', type: 'money' },
        { key: 'outstanding', label: 'Outstanding', type: 'money', render: r => r.outstanding > 0 ? <b>{money(r.outstanding)}</b> : money(r.outstanding) },
        { key: 'is_active', label: '', render: r => r.is_active ? '' : <Badge>Inactive</Badge> },
        { key: 'act', label: '', render: r => <button className="btn small" onClick={e => { e.stopPropagation(); setEdit({ ...blankParty, ...r }) }}>Edit</button> },
      ]} />
      {edit && <Modal title={edit.id ? 'Edit supplier' : 'New supplier'} onClose={() => setEdit(null)} footer={<button className="btn primary" onClick={save} disabled={!edit.name}>Save</button>}>
        <PartyForm value={edit} onChange={setEdit} states={states.data || []} supplier />
      </Modal>}
      {ledger && <Ledger s={ledger} onClose={() => { setLedger(null); reload() }} />}
    </Page>
  )
}

function Ledger({ s, onClose }) {
  const { data, reload } = useLoad(() => api.get(`/api/suppliers/${s.id}/ledger`), [s.id])
  const [pay, setPay] = useState(false)
  return (
    <Modal wide title={`Ledger — ${s.name}`} onClose={onClose} footer={<button className="btn primary" onClick={() => setPay(true)}>Record payment</button>}>
      {data && <>
        <div className="stats">
          <Stat label="Opening" value={money(data.summary.opening_balance)} />
          <Stat label="Purchases" value={money(data.summary.purchases)} />
          <Stat label="Paid" value={money(data.summary.paid)} />
          <Stat label="Returns" value={money(data.summary.returns)} />
          <Stat label="Outstanding" value={money(data.summary.outstanding)} tone="warn" />
        </div>
        <DataTable rows={data.entries} columns={[{ key: 'date', label: 'Date', type: 'date' }, { key: 'type', label: 'Type' }, { key: 'ref', label: 'Reference' },
          { key: 'credit', label: 'Bill (Cr)', type: 'money' }, { key: 'debit', label: 'Paid (Dr)', type: 'money' }, { key: 'balance', label: 'Balance', type: 'money' }]} />
      </>}
      {pay && <PaymentDialog supplierId={s.id} onClose={() => setPay(false)} onDone={() => { setPay(false); reload() }} />}
    </Modal>
  )
}
