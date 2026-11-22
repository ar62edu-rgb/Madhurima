import { useState } from 'react'
import { api, qs } from '../api'
import { Badge, Check, DataTable, ErrorBox, Field, Modal, Page, PeriodFilter, ReasonDialog, Select, Stat, sumBy, useApp, useLoad } from '../components/ui'
import { printBill } from '../print'
import { fmtDateTime, money, ORDER_TYPES, qty, today } from '../utils'

export default function Bills() {
  const [range, setRange] = useState([today(), today()])
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [mode, setMode] = useState('')
  const [open, setOpen] = useState(null)
  const { data, error, reload } = useLoad(() => api.get('/api/bills' + qs({ from_date: range[0], to_date: range[1], q, status, payment_mode: mode })), [range[0], range[1], q, status, mode])
  const rows = data || []
  const active = rows.filter(r => r.status === 'ACTIVE')

  return (
    <Page title="Sales & Bills" subtitle="Billing history, reprint, duplicate invoice, cancellation and credit notes"
          actions={<PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />}>
      <div className="stats">
        <Stat label="Bills" value={active.length} />
        <Stat label="Sales" value={money(sumBy(active, 'grand_total'))} tone="accent" />
        <Stat label="Cash" value={money(sumBy(active, 'cash_amount'))} />
        <Stat label="UPI" value={money(sumBy(active, 'upi_amount'))} />
        <Stat label="GST" value={money(sumBy(active, 'total_tax'))} />
        <Stat label="Cancelled" value={rows.length - active.length} />
      </div>
      <div className="toolbar">
        <input placeholder="Search bill no / customer / phone / UPI ref" value={q} onChange={e => setQ(e.target.value)} />
        <Select value={status} onChange={setStatus} placeholder="All status" options={[['ACTIVE', 'Active'], ['CANCELLED', 'Cancelled']]} />
        <Select value={mode} onChange={setMode} placeholder="All payments" options={[['CASH', 'Cash'], ['UPI', 'UPI'], ['SPLIT', 'Split']]} />
      </div>
      <ErrorBox error={error} />
      <DataTable rows={rows} onRowClick={r => setOpen(r.id)} rowClass={r => r.status === 'CANCELLED' ? 'cancelled' : ''}
        columns={[
          { key: 'bill_no', label: 'Bill No' },
          { key: 'bill_date', label: 'Date / Time', type: 'datetime' },
          { key: 'order_type', label: 'Type', render: r => ORDER_TYPES[r.order_type] + (r.table_name ? ` · ${r.table_name}` : '') },
          { key: 'customer_name', label: 'Customer', render: r => <>{r.customer_name}{r.invoice_type === 'B2B' && <Badge tone="blue">B2B</Badge>}</> },
          { key: 'taxable_amount', label: 'Taxable', type: 'money' },
          { key: 'total_tax', label: 'GST', type: 'money' },
          { key: 'grand_total', label: 'Total', type: 'money' },
          { key: 'payment_mode', label: 'Paid', render: r => <Badge tone={r.payment_mode === 'CASH' ? 'green' : r.payment_mode === 'UPI' ? 'blue' : 'amber'}>{r.payment_mode}</Badge> },
          { key: 'status', label: 'Status', render: r => r.status === 'CANCELLED' ? <Badge tone="red">Cancelled</Badge> : <Badge tone="green">Active</Badge> },
          { key: 'created_by', label: 'By' },
        ]} />
      {open && <BillDetail id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </Page>
  )
}

export function BillDetail({ id, onClose, onChanged }) {
  const { user, settings, toast } = useApp()
  const { data: b, reload, error } = useLoad(() => api.get(`/api/bills/${id}`), [id])
  const [cancel, setCancel] = useState(false)
  const [credit, setCredit] = useState(false)
  const canCancel = user.role !== 'cashier' || user.can_cancel_bill
  if (!b) return <Modal title="Bill" onClose={onClose}><ErrorBox error={error} /></Modal>
  const inter = b.supply_type === 'INTER'
  return (
    <Modal wide title={`Bill ${b.bill_no}`} onClose={onClose} footer={<>
      <button className="btn" onClick={() => printBill(b.id, settings.print_format, true)}>🖨 Reprint (duplicate)</button>
      <button className="btn" onClick={() => printBill(b.id, 'A4', b.print_count > 0)}>🖨 A4 invoice</button>
      {b.status === 'ACTIVE' && b.upi_amount > 0 && (
        <button className="btn" onClick={async () => { await api.post(`/api/bills/${b.id}/upi-verified?verified=${!b.upi_verified}`); reload(); onChanged() }}>
          {b.upi_verified ? 'Mark UPI unverified' : '✓ Mark UPI received'}</button>)}
      {b.status === 'ACTIVE' && user.role !== 'cashier' && <button className="btn" onClick={() => setCredit(true)}>Credit note / return</button>}
      {b.status === 'ACTIVE' && canCancel && !b.credit_notes.length && <button className="btn danger" onClick={() => setCancel(true)}>Cancel bill</button>}
    </>}>
      <div className="detail-grid">
        <div><span className="muted">Date</span> {fmtDateTime(b.bill_date)}</div>
        <div><span className="muted">Order</span> {ORDER_TYPES[b.order_type]} {b.table_name}</div>
        <div><span className="muted">Customer</span> {b.customer_name || 'Walk-in'} {b.customer_phone}</div>
        <div><span className="muted">GSTIN</span> {b.customer_gstin || '-'} ({b.invoice_type})</div>
        <div><span className="muted">Supply</span> {b.supply_type} · POS {b.place_of_supply}-{b.place_of_supply_name}</div>
        <div><span className="muted">Payment</span> {b.payment_mode} — Cash {money(b.cash_amount)} / UPI {money(b.upi_amount)} {b.upi_ref && `(${b.upi_ref})`}</div>
        <div><span className="muted">Printed</span> {b.print_count} time(s)</div>
        <div><span className="muted">Cashier</span> {b.created_by}</div>
      </div>
      {b.status === 'CANCELLED' && <div className="error-box">Cancelled by {b.cancelled_by} on {fmtDateTime(b.cancelled_at)} — {b.cancel_reason}</div>}
      <DataTable rows={b.items} columns={[
        { key: 'item_name', label: 'Item' }, { key: 'hsn', label: 'HSN/SAC' }, { key: 'qty', label: 'Qty', type: 'num' },
        { key: 'rate', label: 'Rate', type: 'money' }, { key: 'discount', label: 'Disc', type: 'money', render: r => money(r.discount + r.bill_discount_share) },
        { key: 'taxable', label: 'Taxable', type: 'money' }, { key: 'gst_rate', label: 'GST %', type: 'pct' },
        ...(inter ? [{ key: 'igst', label: 'IGST', type: 'money' }] : [{ key: 'cgst', label: 'CGST', type: 'money' }, { key: 'sgst', label: 'SGST', type: 'money' }]),
        { key: 'total', label: 'Total', type: 'money' }, { key: 'returned_qty', label: 'Returned', type: 'num' },
      ]} />
      <div className="totals-inline">
        <span>Taxable {money(b.taxable_amount)}</span>
        {b.exempt_amount > 0 && <span>Exempt {money(b.exempt_amount)}</span>}
        <span>CGST {money(b.cgst)}</span><span>SGST {money(b.sgst)}</span><span>IGST {money(b.igst)}</span>
        <span>Round off {money(b.round_off)}</span><b>Total {money(b.grand_total)}</b>
      </div>
      {b.credit_notes.length > 0 && <>
        <h4>Credit notes</h4>
        <DataTable rows={b.credit_notes} columns={[{ key: 'note_no', label: 'No' }, { key: 'note_date', label: 'Date', type: 'date' },
          { key: 'reason', label: 'Reason' }, { key: 'settlement_mode', label: 'Refund' }, { key: 'total', label: 'Total', type: 'money' }]} />
      </>}
      {cancel && <ReasonDialog title={`Cancel bill ${b.bill_no}`} label="Cancellation reason" confirmText="Cancel bill"
        onCancel={() => setCancel(false)} onConfirm={async (reason) => {
          try { await api.post(`/api/bills/${b.id}/cancel`, { reason }); toast('Bill cancelled; stock restored'); setCancel(false); reload(); onChanged() }
          catch (e) { toast(e.message, 'error') }
        }} />}
      {credit && <CreditNoteDialog bill={b} onClose={() => setCredit(false)} onDone={() => { setCredit(false); reload(); onChanged() }} />}
    </Modal>
  )
}

function CreditNoteDialog({ bill, onClose, onDone }) {
  const { toast } = useApp()
  const [qtys, setQtys] = useState({})
  const [reason, setReason] = useState('')
  const [mode, setMode] = useState('CASH')
  const [ref, setRef] = useState('')
  const [restock, setRestock] = useState(false)
  const items = bill.items.filter(i => i.qty - i.returned_qty > 0)
  async function save() {
    const lines = Object.entries(qtys).filter(([, v]) => Number(v) > 0).map(([k, v]) => ({ bill_item_id: Number(k), qty: Number(v) }))
    if (!lines.length) return toast('Enter return quantity', 'error')
    try {
      const n = await api.post('/api/credit-notes', { bill_id: bill.id, items: lines, reason, settlement_mode: mode, settlement_ref: ref, restock })
      toast(`Credit note ${n.note_no} created for ${money(n.total)}`)
      onDone()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Modal title={`Credit note against ${bill.bill_no}`} onClose={onClose} wide footer={<>
      <button className="btn" onClick={onClose}>Back</button>
      <button className="btn primary" onClick={save} disabled={reason.trim().length < 3}>Create credit note</button>
    </>}>
      <table className="table">
        <thead><tr><th>Item</th><th className="r">Billed</th><th className="r">Returned</th><th className="r">Return now</th></tr></thead>
        <tbody>{items.map(i => (
          <tr key={i.id}><td>{i.item_name}</td><td className="r">{qty(i.qty)}</td><td className="r">{qty(i.returned_qty)}</td>
            <td className="r"><input className="narrow" value={qtys[i.id] || ''} onChange={e => setQtys(s => ({ ...s, [i.id]: e.target.value }))} /></td></tr>
        ))}</tbody>
      </table>
      <div className="form-grid">
        <Field label="Reason"><input value={reason} onChange={e => setReason(e.target.value)} /></Field>
        <Field label="Refund / settlement"><Select value={mode} onChange={setMode} options={[['CASH', 'Cash refund'], ['UPI', 'UPI refund'], ['ADJUST', 'Adjust (no refund)']]} /></Field>
        {mode === 'UPI' && <Field label="UPI ref"><input value={ref} onChange={e => setRef(e.target.value)} /></Field>}
        <Check label="Add returned items back to stock (packaged items only)" checked={restock} onChange={setRestock} />
      </div>
    </Modal>
  )
}
