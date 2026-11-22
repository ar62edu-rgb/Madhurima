import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, qs } from '../api'
import { Field, Modal, useApp } from '../components/ui'
import { printBill, printKot } from '../print'
import { money, ORDER_TYPES, qty } from '../utils'

const emptyCustomer = { id: null, name: '', phone: '', gstin: '', address: '', state_code: '' }

export default function POS() {
  const { user, settings, toast } = useApp()
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [tables, setTables] = useState([])
  const [held, setHeld] = useState([])
  const [cat, setCat] = useState(null)
  const [search, setSearch] = useState('')
  const [cart, setCart] = useState([])
  const [orderType, setOrderType] = useState('DINE_IN')
  const [tableId, setTableId] = useState(null)
  const [heldId, setHeldId] = useState(null)
  const [customer, setCustomer] = useState(emptyCustomer)
  const [showCustomer, setShowCustomer] = useState(false)
  const [billDisc, setBillDisc] = useState('')
  const [discPct, setDiscPct] = useState(false)
  const [preview, setPreview] = useState(null)
  const [previewErr, setPreviewErr] = useState('')
  const [paying, setPaying] = useState(false)
  const [lastBill, setLastBill] = useState(null)
  const searchRef = useRef(null)

  const canPrice = user.role === 'admin' || user.can_edit_price
  const canDisc = user.role !== 'cashier' || user.can_discount

  const loadHeld = useCallback(() => api.get('/api/held-orders').then(setHeld), [])
  useEffect(() => {
    Promise.all([api.get('/api/products?pos=true'), api.get('/api/categories'), api.get('/api/tables')])
      .then(([p, c, t]) => { setProducts(p); setCategories(c.filter(x => x.is_active && x.show_in_pos)); setTables(t.filter(x => x.is_active)) })
      .catch(e => toast(e.message, 'error'))
    loadHeld()
  }, [toast, loadHeld])

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase()
    return products.filter(p => (!cat || p.category_id === cat) &&
      (!q || p.name.toLowerCase().includes(q) || p.code.toLowerCase().includes(q) || (p.category_name || '').toLowerCase().includes(q)))
  }, [products, cat, search])

  const subtotal = cart.reduce((s, l) => s + l.qty * l.rate - (Number(l.discount) || 0), 0)
  const billDiscountAmount = discPct ? Math.round(subtotal * (Number(billDisc) || 0)) / 100 : Number(billDisc) || 0

  // server-side preview keeps GST maths in exactly one place
  useEffect(() => {
    if (!cart.length) { setPreview(null); setPreviewErr(''); return }
    const t = setTimeout(() => {
      api.post('/api/bills/preview', payload()).then(p => { setPreview(p); setPreviewErr('') })
        .catch(e => { setPreview(null); setPreviewErr(e.message) })
    }, 150)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart, billDiscountAmount, customer.id, customer.gstin, customer.state_code])

  function payload(extra = {}) {
    return {
      items: cart.map(l => ({ product_id: l.product_id, qty: Number(l.qty), rate: Number(l.rate), discount: Number(l.discount) || 0 })),
      bill_discount: Math.round(billDiscountAmount * 100) / 100,
      customer_id: customer.id, customer_name: customer.name, customer_phone: customer.phone,
      customer_gstin: customer.gstin, customer_address: customer.address, customer_state_code: customer.state_code,
      order_type: orderType, table_name: tables.find(t => t.id === tableId)?.name || '', held_order_id: heldId,
      ...extra,
    }
  }

  function add(p) {
    setCart(c => {
      const i = c.findIndex(l => l.product_id === p.id && l.rate === p.selling_price)
      if (i >= 0) return c.map((l, j) => j === i ? { ...l, qty: Number(l.qty) + 1 } : l)
      return [...c, { product_id: p.id, name: p.name, qty: 1, rate: p.selling_price, base_rate: p.selling_price, discount: 0, kot_qty: 0, unit: p.unit }]
    })
  }
  const update = (i, k, v) => setCart(c => c.map((l, j) => j === i ? { ...l, [k]: v } : l))
  const remove = (i) => setCart(c => c.filter((_, j) => j !== i))

  function reset() {
    setCart([]); setHeldId(null); setTableId(null); setCustomer(emptyCustomer); setBillDisc(''); setPreview(null)
    loadHeld()
    setTimeout(() => searchRef.current?.focus(), 50)
  }

  function openHeld(h) {
    setHeldId(h.id); setTableId(h.table_id); setOrderType(h.order_type)
    setCart(h.items.map(i => ({ ...i, base_rate: i.rate })))
    setCustomer(emptyCustomer)
  }

  function selectTable(t) {
    const h = held.find(x => x.table_id === t.id)
    if (h) openHeld(h)
    else { if (heldId) reset(); setTableId(t.id); setOrderType('DINE_IN'); setHeldId(null); setCart([]) }
  }

  async function saveHeld(sendKot) {
    if (!cart.length) return toast('Add items first', 'error')
    try {
      const body = {
        table_id: orderType === 'DINE_IN' ? tableId : null, order_type: orderType,
        label: customer.name || '', customer_id: customer.id,
        items: cart.map(l => ({ product_id: l.product_id, name: l.name, qty: Number(l.qty), rate: Number(l.rate), discount: Number(l.discount) || 0, kot_qty: l.kot_qty || 0, note: l.note || '' })),
      }
      let h = await api.post('/api/held-orders' + qs({ oid: heldId }), body)
      if (sendKot) {
        try {
          h = await api.post(`/api/held-orders/${h.id}/kot`)
          printKot({ ...h, restaurant: settings.restaurant_name })
          toast(`KOT ${h.kot_no} sent to kitchen`)
        } catch (e) { toast(e.message, 'error') }
      } else toast('Order saved')
      reset()
    } catch (e) { toast(e.message, 'error') }
  }

  async function discardHeld() {
    if (!heldId) return reset()
    if (!confirm('Discard this running order?')) return
    await api.del(`/api/held-orders/${heldId}`).catch(e => toast(e.message, 'error'))
    reset()
  }

  // keyboard shortcuts
  useEffect(() => {
    const k = (e) => {
      if (e.key === 'F2') { e.preventDefault(); searchRef.current?.focus() }
      if (e.key === 'F9' && cart.length && preview) { e.preventDefault(); setPaying(true) }
      if (e.key === 'F8' && cart.length) { e.preventDefault(); saveHeld(true) }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  })

  const t = preview?.totals
  const occupied = new Set(held.filter(h => h.table_id).map(h => h.table_id))
  const others = held.filter(h => !h.table_id)

  return (
    <div className="pos">
      <div className="pos-left">
        <div className="pos-search">
          <input ref={searchRef} placeholder="Search item / code (F2) — Enter adds first match" value={search} autoFocus
                 onChange={e => setSearch(e.target.value)}
                 onKeyDown={e => { if (e.key === 'Enter' && shown[0]) { add(shown[0]); setSearch('') } }} />
        </div>
        <div className="cat-strip">
          <button className={!cat ? 'active' : ''} onClick={() => setCat(null)}>All</button>
          {categories.map(c => <button key={c.id} className={cat === c.id ? 'active' : ''} onClick={() => setCat(c.id)}>{c.name}</button>)}
        </div>
        <div className="product-grid">
          {shown.map(p => (
            <button key={p.id} className="product-tile" onClick={() => add(p)}>
              <span className="pt-name">{p.name}</span>
              <span className="pt-meta"><span>{money(p.selling_price)}</span><span className="muted">{p.code}</span></span>
            </button>
          ))}
          {!shown.length && <div className="empty">No items. Add menu items in Products & Menu.</div>}
        </div>
        <div className="tables-panel">
          <div className="tp-head">Tables & running orders</div>
          <div className="table-chips">
            {tables.map(tb => (
              <button key={tb.id} className={`table-chip ${occupied.has(tb.id) ? 'busy' : ''} ${tableId === tb.id ? 'sel' : ''}`}
                      onClick={() => selectTable(tb)} title={tb.area}>
                {tb.name}
                {occupied.has(tb.id) && <small>{money(held.find(h => h.table_id === tb.id)?.amount)}</small>}
              </button>
            ))}
            {others.map(h => (
              <button key={h.id} className={`table-chip busy ${heldId === h.id ? 'sel' : ''}`} onClick={() => openHeld(h)}>
                {ORDER_TYPES[h.order_type]} #{h.id}<small>{h.label || money(h.amount)}</small>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="pos-right">
        <div className="order-type">
          {Object.entries(ORDER_TYPES).map(([k, v]) => (
            <button key={k} className={orderType === k ? 'active' : ''} onClick={() => { setOrderType(k); if (k !== 'DINE_IN') setTableId(null) }}>{v}</button>
          ))}
        </div>
        <div className="cart-meta">
          <span>{orderType === 'DINE_IN' ? (tableId ? `Table ${tables.find(x => x.id === tableId)?.name}` : 'No table selected') : ORDER_TYPES[orderType]}</span>
          {heldId && <span className="badge amber">Running order #{heldId}</span>}
          <button className="link" onClick={() => setShowCustomer(true)}>
            {customer.name || customer.phone ? `👤 ${customer.name || customer.phone}${customer.gstin ? ' (B2B)' : ''}` : '+ Customer / GSTIN'}
          </button>
        </div>

        <div className="cart">
          {cart.map((l, i) => (
            <div className="cart-line" key={i}>
              <div className="cl-name">
                {l.name}
                {l.kot_qty > 0 && <span className="muted small"> · KOT {qty(l.kot_qty)}</span>}
              </div>
              <div className="qty-box">
                <button onClick={() => Number(l.qty) <= 1 ? remove(i) : update(i, 'qty', Number(l.qty) - 1)}>−</button>
                <input value={l.qty} onChange={e => update(i, 'qty', e.target.value)} inputMode="decimal" />
                <button onClick={() => update(i, 'qty', Number(l.qty) + 1)}>+</button>
              </div>
              <input className="cl-rate" title={canPrice ? 'Rate' : 'Price change not permitted'} value={l.rate} disabled={!canPrice}
                     onChange={e => update(i, 'rate', e.target.value)} inputMode="decimal" />
              <input className="cl-disc" placeholder="Disc ₹" title="Item discount (₹)" value={l.discount || ''} disabled={!canDisc}
                     onChange={e => update(i, 'discount', e.target.value)} inputMode="decimal" />
              <div className="cl-amt">{money(l.qty * l.rate - (Number(l.discount) || 0))}</div>
              <button className="icon-btn" onClick={() => remove(i)} title="Remove">✕</button>
            </div>
          ))}
          {!cart.length && <div className="empty">Tap items to add them to the bill</div>}
        </div>

        <div className="totals">
          <div className="bill-disc">
            <span>Bill discount</span>
            <input value={billDisc} onChange={e => setBillDisc(e.target.value)} disabled={!canDisc} inputMode="decimal" placeholder="0" />
            <button className={`btn small ${discPct ? 'primary' : ''}`} onClick={() => setDiscPct(!discPct)} disabled={!canDisc}>{discPct ? '%' : '₹'}</button>
          </div>
          {previewErr && <div className="error-box small">{previewErr}</div>}
          {t && <>
            <Row l="Gross" v={money(t.gross)} />
            {(t.item_discount > 0 || t.bill_discount > 0) && <Row l="Discount" v={'− ' + money(t.item_discount + t.bill_discount)} />}
            <Row l="Taxable value" v={money(t.taxable)} />
            {t.exempt > 0 && <Row l="Exempt / nil" v={money(t.exempt)} />}
            {preview.supply_type === 'INTER'
              ? <Row l="IGST" v={money(t.igst)} />
              : <><Row l="CGST" v={money(t.cgst)} /><Row l="SGST" v={money(t.sgst)} /></>}
            {t.round_off !== 0 && <Row l="Round off" v={money(t.round_off)} />}
            <div className="grand"><span>Total</span><span>{money(t.grand_total)}</span></div>
          </>}
        </div>
        <div className="pos-actions">
          <button className="btn" onClick={discardHeld} disabled={!cart.length && !heldId}>Clear</button>
          <button className="btn" onClick={() => saveHeld(false)} disabled={!cart.length}>Hold</button>
          <button className="btn amber" onClick={() => saveHeld(true)} disabled={!cart.length}>KOT (F8)</button>
          <button className="btn primary big" onClick={() => setPaying(true)} disabled={!t}>Pay {t ? money(t.grand_total) : ''} (F9)</button>
        </div>
        {lastBill && (
          <div className="last-bill">
            Last bill <b>{lastBill.bill_no}</b> · {money(lastBill.grand_total)}
            {lastBill.change_returned > 0 && <> · Change <b>{money(lastBill.change_returned)}</b></>}
            <button className="link" onClick={() => printBill(lastBill.id, settings.print_format, true)}>Reprint</button>
          </div>
        )}
      </div>

      {showCustomer && <CustomerDialog value={customer} onClose={() => setShowCustomer(false)} onSave={c => { setCustomer(c); setShowCustomer(false) }} />}
      {paying && t && (
        <PaymentDialog total={t.grand_total} onClose={() => setPaying(false)}
          onPay={async (pay) => {
            try {
              const bill = await api.post('/api/bills', payload(pay))
              setPaying(false)
              setLastBill(bill)
              toast(`Bill ${bill.bill_no} saved`)
              for (let n = 0; n < Number(settings.print_copies || 1); n++) printBill(bill.id, settings.print_format)
              reset()
            } catch (e) { toast(e.message, 'error') }
          }} />
      )}
    </div>
  )
}

function Row({ l, v }) { return <div className="tot-row"><span>{l}</span><span>{v}</span></div> }

function PaymentDialog({ total, onClose, onPay }) {
  const [mode, setMode] = useState('CASH')
  const [cash, setCash] = useState(String(total))
  const [upi, setUpi] = useState('')
  const [tendered, setTendered] = useState('')
  const [ref, setRef] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (mode === 'CASH') { setCash(String(total)); setUpi('') }
    if (mode === 'UPI') { setUpi(String(total)); setCash('') }
    if (mode === 'SPLIT') { setCash(''); setUpi('') }
  }, [mode, total])

  const c = Number(cash) || 0, u = Number(upi) || 0
  const diff = Math.round((total - c - u) * 100) / 100
  const change = tendered ? Math.round((Number(tendered) - c) * 100) / 100 : 0
  const ok = Math.abs(diff) < 0.01 && (!tendered || Number(tendered) >= c)

  async function submit() {
    setBusy(true)
    try { await onPay({ cash_amount: c, upi_amount: u, upi_ref: ref, cash_tendered: Number(tendered) || c }) } finally { setBusy(false) }
  }

  return (
    <Modal title={`Payment — ${money(total)}`} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Back</button>
      <button className="btn primary big" disabled={!ok || busy} onClick={submit}>Save & Print</button>
    </>}>
      <div className="seg">
        {[['CASH', '💵 Cash'], ['UPI', '📱 UPI'], ['SPLIT', '➗ Cash + UPI']].map(([k, l]) =>
          <button key={k} className={mode === k ? 'active' : ''} onClick={() => setMode(k)}>{l}</button>)}
      </div>
      <div className="form-grid">
        {mode !== 'UPI' && <Field label="Cash amount"><input value={cash} onChange={e => { setCash(e.target.value); if (mode === 'SPLIT') setUpi(String(Math.max(0, Math.round((total - (Number(e.target.value) || 0)) * 100) / 100))) }} inputMode="decimal" autoFocus /></Field>}
        {mode !== 'CASH' && <Field label="UPI amount"><input value={upi} onChange={e => { setUpi(e.target.value); if (mode === 'SPLIT') setCash(String(Math.max(0, Math.round((total - (Number(e.target.value) || 0)) * 100) / 100))) }} inputMode="decimal" autoFocus={mode === 'UPI'} /></Field>}
        {mode !== 'CASH' && <Field label="UPI transaction ref (UTR)" hint="Optional but recommended for reconciliation"><input value={ref} onChange={e => setRef(e.target.value)} /></Field>}
        {mode !== 'UPI' && <Field label="Cash received from customer" hint={change > 0 ? `Return change: ${money(change)}` : ''}><input value={tendered} onChange={e => setTendered(e.target.value)} inputMode="decimal" placeholder={String(c)} onKeyDown={e => e.key === 'Enter' && ok && submit()} /></Field>}
      </div>
      {Math.abs(diff) >= 0.01 && <div className="error-box">{diff > 0 ? `Short by ${money(diff)}` : `Excess by ${money(-diff)}`} — payment must equal the bill total.</div>}
      {change > 0 && <div className="change-box">Change to return: <b>{money(change)}</b></div>}
    </Modal>
  )
}

function CustomerDialog({ value, onClose, onSave }) {
  const { toast } = useApp()
  const [c, setC] = useState(value)
  const [results, setResults] = useState([])
  const [states, setStates] = useState([])
  const [q, setQ] = useState('')
  useEffect(() => { api.get('/api/states').then(setStates) }, [])
  useEffect(() => {
    if (q.length < 2) { setResults([]); return }
    const t = setTimeout(() => api.get('/api/customers' + qs({ q })).then(setResults), 200)
    return () => clearTimeout(t)
  }, [q])
  const set = (k) => (e) => setC(s => ({ ...s, [k]: e.target.value, ...(k !== 'id' ? {} : {}) }))

  async function saveNew() {
    try {
      const saved = await api.post('/api/customers', { name: c.name, phone: c.phone, gstin: c.gstin, address: c.address, state_code: c.state_code })
      onSave({ ...emptyCustomer, ...saved })
      toast('Customer saved')
    } catch (e) { toast(e.message, 'error') }
  }

  return (
    <Modal title="Customer" onClose={onClose} footer={<>
      <button className="btn" onClick={() => onSave(emptyCustomer)}>Walk-in (clear)</button>
      {!c.id && c.name && <button className="btn" onClick={saveNew}>Save as new customer</button>}
      <button className="btn primary" onClick={() => onSave(c)}>Use on this bill</button>
    </>}>
      <Field label="Search existing (name / phone / GSTIN)"><input value={q} onChange={e => setQ(e.target.value)} autoFocus /></Field>
      {results.length > 0 && (
        <div className="pick-list">
          {results.map(r => <button key={r.id} onClick={() => { setC({ ...emptyCustomer, ...r }); setResults([]); setQ('') }}>
            <b>{r.name}</b> {r.phone} {r.gstin && <span className="badge blue">{r.gstin}</span>}</button>)}
        </div>
      )}
      <div className="form-grid">
        <Field label="Name"><input value={c.name} onChange={set('name')} /></Field>
        <Field label="Phone"><input value={c.phone} onChange={set('phone')} /></Field>
        <Field label="GSTIN (for B2B invoice)"><input value={c.gstin} onChange={e => setC(s => ({ ...s, gstin: e.target.value.toUpperCase(), state_code: e.target.value.length >= 2 ? e.target.value.slice(0, 2) : s.state_code }))} maxLength={15} /></Field>
        <Field label="State (place of supply)">
          <select value={c.state_code} onChange={set('state_code')}>
            <option value="">Same as restaurant</option>
            {states.map(s => <option key={s.code} value={s.code}>{s.code} - {s.name}</option>)}
          </select>
        </Field>
        <Field label="Address" span={2}><input value={c.address} onChange={set('address')} /></Field>
      </div>
      {c.id && <div className="muted small">Linked to saved customer #{c.id}. Edits here apply to this bill only.</div>}
    </Modal>
  )
}
