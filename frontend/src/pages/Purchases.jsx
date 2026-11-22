import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { Badge, Check, DataTable, ErrorBox, Field, Modal, Page, PeriodFilter, ReasonDialog, Select, Stat, sumBy, useApp, useLoad } from '../components/ui'
import { fmtDate, money, presetRange, qty, today } from '../utils'

const STATUS_TONE = { PAID: 'green', PARTIAL: 'amber', UNPAID: 'red', CANCELLED: 'grey' }

export default function Purchases() {
  const [range, setRange] = useState(presetRange('month'))
  const [sup, setSup] = useState('')
  const [creating, setCreating] = useState(false)
  const [open, setOpen] = useState(null)
  const suppliers = useLoad(() => api.get('/api/suppliers'), [])
  const { data, error, reload } = useLoad(() => api.get('/api/purchases' + qs({ from_date: range[0], to_date: range[1], supplier_id: sup })), [range[0], range[1], sup])
  const active = (data || []).filter(p => p.status === 'ACTIVE')
  return (
    <Page title="Purchases" subtitle="Purchase entries update stock automatically"
          actions={<button className="btn primary" onClick={() => setCreating(true)}>+ New purchase</button>}>
      <div className="toolbar">
        <PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />
        <Select value={sup} onChange={setSup} placeholder="All suppliers" options={(suppliers.data || []).map(s => [s.id, s.name])} />
      </div>
      <div className="stats">
        <Stat label="Purchases" value={active.length} />
        <Stat label="Total value" value={money(sumBy(active, 'grand_total'))} tone="accent" />
        <Stat label="Input GST" value={money(sumBy(active, 'total_tax'))} />
        <Stat label="Unpaid balance" value={money(sumBy(active, 'balance'))} tone="warn" />
      </div>
      <ErrorBox error={error} />
      <DataTable rows={data} onRowClick={r => setOpen(r.id)} rowClass={r => r.status === 'CANCELLED' ? 'cancelled' : ''} columns={[
        { key: 'purchase_no', label: 'Purchase No' }, { key: 'invoice_date', label: 'Inv Date', type: 'date' },
        { key: 'supplier_name', label: 'Supplier' }, { key: 'supplier_invoice_no', label: 'Supplier Inv' },
        { key: 'taxable_amount', label: 'Taxable', type: 'money' }, { key: 'total_tax', label: 'GST', type: 'money' },
        { key: 'grand_total', label: 'Total', type: 'money' }, { key: 'paid_amount', label: 'Paid', type: 'money' },
        { key: 'balance', label: 'Balance', type: 'money' },
        { key: 'payment_status', label: 'Status', render: r => <Badge tone={STATUS_TONE[r.payment_status]}>{r.payment_status}</Badge> },
        { key: 'attachment_name', label: '📎', render: r => r.attachment_name ? '📎' : '' },
      ]} />
      {creating && <PurchaseForm suppliers={suppliers.data || []} onClose={() => setCreating(false)} onSaved={(p) => { setCreating(false); reload(); setOpen(p.id) }} reloadSuppliers={suppliers.reload} />}
      {open && <PurchaseDetail id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </Page>
  )
}

function PurchaseForm({ suppliers, onClose, onSaved }) {
  const { toast } = useApp()
  const [products, setProducts] = useState([])
  const [f, setF] = useState({ supplier_id: '', supplier_invoice_no: '', invoice_date: today(), supply_type: 'AUTO', other_charges: '', round_off: true, update_purchase_price: true, paid_cash: '', paid_upi: '', upi_ref: '', notes: '' })
  const [lines, setLines] = useState([{ product_id: '', qty: '', rate: '', discount: '', gst_rate: 5 }])
  const [preview, setPreview] = useState(null)
  const [file, setFile] = useState(null)
  useEffect(() => { api.get('/api/products?active_only=true').then(setProducts) }, [])

  const body = () => ({
    ...f, supplier_id: Number(f.supplier_id), other_charges: Number(f.other_charges) || 0,
    paid_cash: Number(f.paid_cash) || 0, paid_upi: Number(f.paid_upi) || 0,
    items: lines.filter(l => l.product_id && Number(l.qty) > 0).map(l => ({ product_id: Number(l.product_id), qty: Number(l.qty), rate: Number(l.rate) || 0, discount: Number(l.discount) || 0, gst_rate: Number(l.gst_rate) || 0 })),
  })

  useEffect(() => {
    const b = body()
    if (!b.supplier_id || !b.items.length) { setPreview(null); return }
    const t = setTimeout(() => api.post('/api/purchases/preview', b).then(setPreview).catch(() => setPreview(null)), 200)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f, lines])

  const setLine = (i, k, v) => setLines(ls => ls.map((l, j) => {
    if (j !== i) return l
    const n = { ...l, [k]: v }
    if (k === 'product_id') { const p = products.find(x => x.id === Number(v)); if (p) { n.rate = p.purchase_price || ''; n.gst_rate = p.gst_rate } }
    return n
  }))

  async function save() {
    try {
      const p = await api.post('/api/purchases', body())
      if (file) {
        const fd = new FormData(); fd.append('file', file)
        await api.upload(`/api/purchases/${p.id}/attachment`, fd).catch(e => toast('Saved, but attachment failed: ' + e.message, 'error'))
      }
      toast(`Purchase ${p.purchase_no} saved; stock updated`)
      onSaved(p)
    } catch (e) { toast(e.message, 'error') }
  }
  const t = preview?.totals
  return (
    <Modal wide title="New purchase entry" onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={!t || !f.supplier_invoice_no}>Save purchase {t ? money(t.grand_total) : ''}</button>
    </>}>
      <div className="form-grid three">
        <Field label="Supplier"><Select value={f.supplier_id} onChange={v => setF({ ...f, supplier_id: v })} placeholder="Select supplier" options={suppliers.filter(s => s.is_active).map(s => [s.id, s.name])} /></Field>
        <Field label="Supplier invoice no"><input value={f.supplier_invoice_no} onChange={e => setF({ ...f, supplier_invoice_no: e.target.value })} /></Field>
        <Field label="Invoice date"><input type="date" value={f.invoice_date} onChange={e => setF({ ...f, invoice_date: e.target.value })} /></Field>
        <Field label="Supply type" hint={preview ? `Using ${preview.supply_type === 'INTER' ? 'IGST' : 'CGST + SGST'}` : ''}><Select value={f.supply_type} onChange={v => setF({ ...f, supply_type: v })} options={[['AUTO', 'Auto (from supplier state)'], ['INTRA', 'Intra-state (CGST+SGST)'], ['INTER', 'Inter-state (IGST)']]} /></Field>
        <Field label="Other charges (freight etc.) ₹"><input value={f.other_charges} onChange={e => setF({ ...f, other_charges: e.target.value })} inputMode="decimal" /></Field>
        <Field label="Invoice attachment (PDF/JPG/PNG)"><input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e => setFile(e.target.files[0])} /></Field>
      </div>
      {suppliers.length === 0 && <div className="error-box">Add a supplier first (Suppliers page).</div>}
      <table className="table">
        <thead><tr><th>Product</th><th className="r">Qty</th><th className="r">Rate (ex-GST)</th><th className="r">Discount ₹</th><th className="r">GST %</th><th className="r">Taxable</th><th className="r">Total</th><th></th></tr></thead>
        <tbody>{lines.map((l, i) => {
          const valid = lines.slice(0, i + 1).filter(x => x.product_id && Number(x.qty) > 0).length - 1
          const pl = l.product_id && Number(l.qty) > 0 ? preview?.lines?.[valid] : null
          return (
            <tr key={i}>
              <td><select value={l.product_id} onChange={e => setLine(i, 'product_id', e.target.value)}>
                <option value="">Select</option>{products.map(p => <option key={p.id} value={p.id}>{p.name} ({p.unit})</option>)}</select></td>
              <td className="r"><input className="narrow" value={l.qty} onChange={e => setLine(i, 'qty', e.target.value)} inputMode="decimal" /></td>
              <td className="r"><input className="narrow" value={l.rate} onChange={e => setLine(i, 'rate', e.target.value)} inputMode="decimal" /></td>
              <td className="r"><input className="narrow" value={l.discount} onChange={e => setLine(i, 'discount', e.target.value)} inputMode="decimal" /></td>
              <td className="r"><input className="narrow" value={l.gst_rate} onChange={e => setLine(i, 'gst_rate', e.target.value)} inputMode="decimal" /></td>
              <td className="r">{pl ? money(pl.taxable) : ''}</td><td className="r">{pl ? money(pl.total) : ''}</td>
              <td><button className="icon-btn" onClick={() => setLines(ls => ls.filter((_, j) => j !== i))}>✕</button></td>
            </tr>
          )
        })}</tbody>
      </table>
      <button className="btn small" onClick={() => setLines(ls => [...ls, { product_id: '', qty: '', rate: '', discount: '', gst_rate: 5 }])}>+ Add line</button>
      {t && <div className="totals-inline">
        <span>Taxable {money(t.taxable + t.exempt)}</span><span>CGST {money(t.cgst)}</span><span>SGST {money(t.sgst)}</span><span>IGST {money(t.igst)}</span>
        <span>Round off {money(t.round_off)}</span><b>Total {money(t.grand_total)}</b></div>}
      <div className="form-grid three">
        <Field label="Paid now in cash ₹"><input value={f.paid_cash} onChange={e => setF({ ...f, paid_cash: e.target.value })} inputMode="decimal" /></Field>
        <Field label="Paid now by UPI ₹"><input value={f.paid_upi} onChange={e => setF({ ...f, paid_upi: e.target.value })} inputMode="decimal" /></Field>
        <Field label="UPI ref"><input value={f.upi_ref} onChange={e => setF({ ...f, upi_ref: e.target.value })} /></Field>
        <Field label="Notes" span={2}><input value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} /></Field>
        <div className="col">
          <Check label="Round off total" checked={f.round_off} onChange={v => setF({ ...f, round_off: v })} />
          <Check label="Update product cost price" checked={f.update_purchase_price} onChange={v => setF({ ...f, update_purchase_price: v })} />
        </div>
      </div>
    </Modal>
  )
}

function PurchaseDetail({ id, onClose, onChanged }) {
  const { toast } = useApp()
  const { data: p, reload } = useLoad(() => api.get(`/api/purchases/${id}`), [id])
  const [cancel, setCancel] = useState(false)
  const [ret, setRet] = useState(false)
  const [pay, setPay] = useState(false)
  if (!p) return null
  const refresh = () => { reload(); onChanged() }
  async function upload(e) {
    const fd = new FormData(); fd.append('file', e.target.files[0])
    try { await api.upload(`/api/purchases/${p.id}/attachment`, fd); toast('Attachment uploaded'); refresh() } catch (err) { toast(err.message, 'error') }
  }
  return (
    <Modal wide title={`Purchase ${p.purchase_no}`} onClose={onClose} footer={p.status === 'ACTIVE' && <>
      <label className="btn">📎 {p.attachment_name ? 'Replace' : 'Attach'} invoice<input type="file" hidden accept=".pdf,.jpg,.jpeg,.png" onChange={upload} /></label>
      {p.balance > 0 && <button className="btn primary" onClick={() => setPay(true)}>Record payment</button>}
      <button className="btn" onClick={() => setRet(true)}>Purchase return</button>
      {!p.debit_notes.length && <button className="btn danger" onClick={() => setCancel(true)}>Cancel purchase</button>}
    </>}>
      <div className="detail-grid">
        <div><span className="muted">Supplier</span> {p.supplier_name} {p.supplier_gstin}</div>
        <div><span className="muted">Invoice</span> {p.supplier_invoice_no} · {fmtDate(p.invoice_date)}</div>
        <div><span className="muted">Supply</span> {p.supply_type}</div>
        <div><span className="muted">Status</span> <Badge tone={STATUS_TONE[p.payment_status]}>{p.payment_status}</Badge></div>
        <div><span className="muted">Paid</span> {money(p.paid_amount)} · Balance {money(p.balance)}</div>
        <div><span className="muted">Attachment</span> {p.attachment_name
          ? <button className="link" onClick={() => api.download(`/api/purchases/${p.id}/attachment`, p.attachment_name)}>{p.attachment_name}</button> : '—'}</div>
      </div>
      {p.status === 'CANCELLED' && <div className="error-box">Cancelled — {p.cancel_reason}</div>}
      <DataTable rows={p.items} columns={[{ key: 'item_name', label: 'Item' }, { key: 'qty', label: 'Qty', type: 'num' }, { key: 'unit', label: 'Unit' },
        { key: 'rate', label: 'Rate', type: 'money' }, { key: 'discount', label: 'Disc', type: 'money' }, { key: 'taxable', label: 'Taxable', type: 'money' },
        { key: 'gst_rate', label: 'GST %', type: 'pct' }, { key: 'cgst', label: 'CGST', type: 'money' }, { key: 'sgst', label: 'SGST', type: 'money' },
        { key: 'igst', label: 'IGST', type: 'money' }, { key: 'total', label: 'Total', type: 'money' }, { key: 'returned_qty', label: 'Returned', type: 'num' }]} />
      <div className="totals-inline"><span>Other charges {money(p.other_charges)}</span><span>Round off {money(p.round_off)}</span><b>Total {money(p.grand_total)}</b></div>
      {p.debit_notes.length > 0 && <>
        <h4>Purchase returns (debit notes)</h4>
        <DataTable rows={p.debit_notes} columns={[{ key: 'note_no', label: 'No' }, { key: 'note_date', label: 'Date', type: 'date' }, { key: 'reason', label: 'Reason' },
          { key: 'settlement_mode', label: 'Settled' }, { key: 'total', label: 'Total', type: 'money' }]} />
      </>}
      {cancel && <ReasonDialog title="Cancel purchase" onCancel={() => setCancel(false)} confirmText="Cancel purchase (reverses stock)"
        onConfirm={async (reason) => { try { await api.post(`/api/purchases/${p.id}/cancel`, { reason }); setCancel(false); refresh(); toast('Purchase cancelled') } catch (e) { toast(e.message, 'error') } }} />}
      {ret && <ReturnDialog p={p} onClose={() => setRet(false)} onDone={() => { setRet(false); refresh() }} />}
      {pay && <PaymentDialog supplierId={p.supplier_id} purchase={p} onClose={() => setPay(false)} onDone={() => { setPay(false); refresh() }} />}
    </Modal>
  )
}

function ReturnDialog({ p, onClose, onDone }) {
  const { toast } = useApp()
  const [qtys, setQtys] = useState({})
  const [reason, setReason] = useState('')
  const [mode, setMode] = useState('ADJUST')
  async function save() {
    const items = Object.entries(qtys).filter(([, v]) => Number(v) > 0).map(([k, v]) => ({ purchase_item_id: Number(k), qty: Number(v) }))
    try { const n = await api.post(`/api/purchases/${p.id}/return`, { items, reason, settlement_mode: mode }); toast(`Debit note ${n.note_no} created`); onDone() }
    catch (e) { toast(e.message, 'error') }
  }
  return (
    <Modal title="Purchase return" onClose={onClose} footer={<button className="btn primary" onClick={save} disabled={reason.length < 3}>Create debit note</button>}>
      <table className="table"><thead><tr><th>Item</th><th className="r">Purchased</th><th className="r">Returned</th><th className="r">Return now</th></tr></thead>
        <tbody>{p.items.map(i => <tr key={i.id}><td>{i.item_name}</td><td className="r">{qty(i.qty)}</td><td className="r">{qty(i.returned_qty)}</td>
          <td className="r"><input className="narrow" value={qtys[i.id] || ''} onChange={e => setQtys(s => ({ ...s, [i.id]: e.target.value }))} /></td></tr>)}</tbody></table>
      <Field label="Reason"><input value={reason} onChange={e => setReason(e.target.value)} /></Field>
      <Field label="Settlement"><Select value={mode} onChange={setMode} options={[['ADJUST', 'Adjust against supplier balance'], ['CASH', 'Supplier refunded cash'], ['UPI', 'Supplier refunded by UPI']]} /></Field>
    </Modal>
  )
}

export function PaymentDialog({ supplierId, purchase, onClose, onDone }) {
  const { toast } = useApp()
  const [f, setF] = useState({ payment_date: today(), amount: purchase ? String(purchase.balance) : '', mode: 'CASH', reference: '', remarks: '' })
  async function save() {
    try {
      await api.post('/api/supplier-payments', { ...f, supplier_id: supplierId, purchase_id: purchase?.id || null, amount: Number(f.amount) })
      toast('Payment recorded'); onDone()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Modal title={purchase ? `Pay against ${purchase.purchase_no}` : 'Supplier payment'} onClose={onClose} footer={<button className="btn primary" onClick={save} disabled={!(Number(f.amount) > 0)}>Save payment</button>}>
      <div className="form-grid">
        <Field label="Date"><input type="date" value={f.payment_date} onChange={e => setF({ ...f, payment_date: e.target.value })} /></Field>
        <Field label="Amount ₹"><input value={f.amount} onChange={e => setF({ ...f, amount: e.target.value })} inputMode="decimal" autoFocus /></Field>
        <Field label="Mode"><Select value={f.mode} onChange={v => setF({ ...f, mode: v })} options={[['CASH', 'Cash'], ['UPI', 'UPI']]} /></Field>
        <Field label="Reference"><input value={f.reference} onChange={e => setF({ ...f, reference: e.target.value })} /></Field>
        <Field label="Remarks" span={2}><input value={f.remarks} onChange={e => setF({ ...f, remarks: e.target.value })} /></Field>
      </div>
    </Modal>
  )
}
