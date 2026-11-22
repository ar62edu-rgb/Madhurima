import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../components/ui'
import { amountInWords, fmtDateTime, money, num2, ORDER_TYPES, qty } from '../utils'

function usePrintWhenReady(ready, after) {
  useEffect(() => {
    if (!ready) return
    const t = setTimeout(() => {
      window.onafterprint = () => after?.()
      window.print()
    }, 250)
    return () => clearTimeout(t)
  }, [ready, after])
}

export function PrintBill() {
  const { id } = useParams()
  const [sp] = useSearchParams()
  const { settings } = useApp()
  const [bill, setBill] = useState(null)
  const size = sp.get('size') || settings?.print_format || '80'
  const dup = sp.get('dup') === '1'

  useEffect(() => {
    api.get(`/api/bills/${id}`).then(async b => {
      setBill(b)
      await api.post(`/api/bills/${id}/printed${dup ? '?duplicate=true' : ''}`).catch(() => {})
    })
  }, [id, dup])
  usePrintWhenReady(bill && settings)

  if (!bill || !settings) return <div style={{ padding: 20 }}>Preparing bill…</div>
  const reprint = dup || bill.print_count > 0
  return (
    <div className={`print-root size-${size}`}>
      <style>{`@page { size: ${size === 'A4' ? 'A4' : `${size}mm auto`}; margin: ${size === 'A4' ? '12mm' : '2mm'}; }`}</style>
      {size === 'A4' ? <A4Invoice bill={bill} s={settings} reprint={reprint} /> : <ThermalInvoice bill={bill} s={settings} reprint={reprint} />}
    </div>
  )
}

function title(bill, s) {
  if (s.gst_registration_type !== 'REGULAR') return 'BILL OF SUPPLY'
  return s.invoice_title || 'TAX INVOICE'
}

function payLine(b) {
  if (b.payment_mode === 'SPLIT') return `Cash ${num2(b.cash_amount)} + UPI ${num2(b.upi_amount)}`
  return b.payment_mode
}

function ThermalInvoice({ bill: b, s, reprint }) {
  const inter = b.supply_type === 'INTER'
  return (
    <div className="thermal">
      <div className="c b big">{s.restaurant_name}</div>
      {s.address && <div className="c">{s.address}{s.city ? ', ' + s.city : ''}{s.pincode ? ' - ' + s.pincode : ''}</div>}
      {s.phone && <div className="c">Ph: {s.phone}</div>}
      {s.gstin && <div className="c">GSTIN: {s.gstin}</div>}
      {s.fssai && <div className="c">FSSAI: {s.fssai}</div>}
      <div className="c b sep">{title(b, s)}{reprint ? ' (DUPLICATE)' : ''}</div>
      {b.status === 'CANCELLED' && <div className="c b">*** CANCELLED ***</div>}
      <div className="kv"><span>Bill: <b>{b.bill_no}</b></span><span>{fmtDateTime(b.bill_date)}</span></div>
      <div className="kv"><span>{ORDER_TYPES[b.order_type]}{b.table_name ? ` · Table ${b.table_name}` : ''}</span><span>{b.created_by}</span></div>
      {(b.customer_name || b.customer_phone) && <div>Customer: {b.customer_name} {b.customer_phone}</div>}
      {b.customer_gstin && <div>Cust GSTIN: {b.customer_gstin}</div>}
      {inter && <div>Place of supply: {b.place_of_supply}-{b.place_of_supply_name}</div>}
      <table className="t-items">
        <thead><tr><th className="l">Item</th><th>Qty</th><th>Rate</th><th>Amt</th></tr></thead>
        <tbody>
          {b.items.map(i => (
            <tr key={i.id}>
              <td className="l">{i.item_name}<div className="tiny">HSN {i.hsn} · GST {i.gst_rate}%{i.discount ? ` · Disc ${num2(i.discount)}` : ''}</div></td>
              <td>{qty(i.qty)}</td><td>{num2(i.rate)}</td><td>{num2(i.gross - i.discount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="sep" />
      <div className="kv"><span>Sub total</span><span>{num2(b.gross_amount - b.item_discount)}</span></div>
      {b.bill_discount > 0 && <div className="kv"><span>Bill discount</span><span>-{num2(b.bill_discount)}</span></div>}
      <div className="kv"><span>Taxable value</span><span>{num2(b.taxable_amount)}</span></div>
      {b.exempt_amount > 0 && <div className="kv"><span>Exempt / nil</span><span>{num2(b.exempt_amount)}</span></div>}
      {b.gst_breakup.filter(g => g.gst_rate > 0).map(g => inter
        ? <div className="kv" key={g.gst_rate}><span>IGST @{g.gst_rate}%</span><span>{num2(g.igst)}</span></div>
        : <div key={g.gst_rate}>
            <div className="kv"><span>CGST @{g.gst_rate / 2}%</span><span>{num2(g.cgst)}</span></div>
            <div className="kv"><span>SGST @{g.gst_rate / 2}%</span><span>{num2(g.sgst)}</span></div>
          </div>)}
      {b.round_off !== 0 && <div className="kv"><span>Round off</span><span>{num2(b.round_off)}</span></div>}
      <div className="kv grand"><span>GRAND TOTAL</span><span>₹{num2(b.grand_total)}</span></div>
      <div className="sep" />
      <div className="kv"><span>Paid by</span><span>{payLine(b)}</span></div>
      <div className="kv"><span>Amount paid</span><span>{num2(b.cash_amount + b.upi_amount)}</span></div>
      {b.upi_ref && <div className="kv"><span>UPI Ref</span><span>{b.upi_ref}</span></div>}
      {b.change_returned > 0 && <div className="kv"><span>Cash received / change</span><span>{num2(b.cash_tendered)} / {num2(b.change_returned)}</span></div>}
      {s.show_upi_qr_text && <div className="c tiny">Pay by UPI: {s.show_upi_qr_text}</div>}
      <div className="c sep">{s.invoice_footer}</div>
    </div>
  )
}

function A4Invoice({ bill: b, s, reprint }) {
  const inter = b.supply_type === 'INTER'
  return (
    <div className="a4">
      <div className="a4-head">
        <div>
          <h1>{s.restaurant_name}</h1>
          <div>{s.address}{s.city ? ', ' + s.city : ''}{s.pincode ? ' - ' + s.pincode : ''}</div>
          <div>{s.phone && `Phone: ${s.phone}`} {s.email && ` · ${s.email}`}</div>
          <div>GSTIN: <b>{s.gstin || '-'}</b> · State: {s.state} ({s.state_code}) · FSSAI: {s.fssai || '-'}</div>
        </div>
        <div className="a4-title">
          <h2>{title(b, s)}</h2>
          {reprint && <div>DUPLICATE</div>}
          {b.status === 'CANCELLED' && <div className="cancel">CANCELLED</div>}
        </div>
      </div>
      <div className="a4-meta">
        <div>
          <div><b>Bill to:</b> {b.customer_name || 'Walk-in customer'}</div>
          {b.customer_address && <div>{b.customer_address}</div>}
          {b.customer_phone && <div>Phone: {b.customer_phone}</div>}
          {b.customer_gstin && <div>GSTIN: {b.customer_gstin}</div>}
          <div>Place of supply: {b.place_of_supply}-{b.place_of_supply_name}</div>
        </div>
        <div>
          <div>Invoice No: <b>{b.bill_no}</b></div>
          <div>Date & time: {fmtDateTime(b.bill_date)}</div>
          <div>Order: {ORDER_TYPES[b.order_type]}{b.table_name ? ` · Table ${b.table_name}` : ''}</div>
          <div>Cashier: {b.created_by}</div>
        </div>
      </div>
      <table className="a4-table">
        <thead>
          <tr><th>#</th><th className="l">Item</th><th>HSN/SAC</th><th>Qty</th><th>Rate</th><th>Discount</th><th>Taxable</th><th>GST %</th>
            {inter ? <th>IGST</th> : <><th>CGST</th><th>SGST</th></>}<th>Total</th></tr>
        </thead>
        <tbody>
          {b.items.map((i, n) => (
            <tr key={i.id}>
              <td>{n + 1}</td><td className="l">{i.item_name}</td><td>{i.hsn}</td><td>{qty(i.qty)} {i.unit}</td><td>{num2(i.rate)}</td>
              <td>{num2(i.discount + i.bill_discount_share)}</td><td>{num2(i.taxable)}</td><td>{i.gst_rate}</td>
              {inter ? <td>{num2(i.igst)}</td> : <><td>{num2(i.cgst)}</td><td>{num2(i.sgst)}</td></>}<td>{num2(i.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="a4-bottom">
        <div>
          <table className="a4-table small">
            <thead><tr><th>GST %</th><th>Taxable</th>{inter ? <th>IGST</th> : <><th>CGST</th><th>SGST</th></>}</tr></thead>
            <tbody>{b.gst_breakup.map(g => (
              <tr key={g.gst_rate}><td>{g.gst_rate}</td><td>{num2(g.taxable)}</td>{inter ? <td>{num2(g.igst)}</td> : <><td>{num2(g.cgst)}</td><td>{num2(g.sgst)}</td></>}</tr>
            ))}</tbody>
          </table>
          <p><b>Amount in words:</b> {amountInWords(b.grand_total)}</p>
          <p>Payment: <b>{payLine(b)}</b> · Amount paid {money(b.cash_amount + b.upi_amount)}{b.upi_ref ? ` · UPI Ref ${b.upi_ref}` : ''}</p>
        </div>
        <div className="a4-totals">
          <div><span>Gross</span><span>{num2(b.gross_amount)}</span></div>
          <div><span>Discount</span><span>-{num2(b.item_discount + b.bill_discount)}</span></div>
          <div><span>Taxable value</span><span>{num2(b.taxable_amount)}</span></div>
          {b.exempt_amount > 0 && <div><span>Exempt / nil</span><span>{num2(b.exempt_amount)}</span></div>}
          {inter ? <div><span>IGST</span><span>{num2(b.igst)}</span></div>
            : <><div><span>CGST</span><span>{num2(b.cgst)}</span></div><div><span>SGST</span><span>{num2(b.sgst)}</span></div></>}
          <div><span>Round off</span><span>{num2(b.round_off)}</span></div>
          <div className="grand"><span>Grand total</span><span>{money(b.grand_total)}</span></div>
        </div>
      </div>
      <div className="a4-foot">
        <div>{s.invoice_footer}</div>
        <div className="sign">For {s.restaurant_name}<br /><br />Authorised signatory</div>
      </div>
    </div>
  )
}

export function PrintKot() {
  const [kot] = useState(() => { try { return JSON.parse(localStorage.getItem('mfr_kot') || 'null') } catch { return null } })
  usePrintWhenReady(!!kot)
  if (!kot) return <div>No KOT</div>
  return (
    <div className="print-root size-80">
      <style>{'@page { size: 80mm auto; margin: 2mm; }'}</style>
      <div className="thermal kot">
        <div className="c b big">KITCHEN ORDER TICKET</div>
        <div className="kv"><span>KOT <b>{kot.kot_no}</b></span><span>{fmtDateTime(kot.kot_time)}</span></div>
        <div className="kv b big"><span>{kot.table_name ? `Table ${kot.table_name}` : ORDER_TYPES[kot.order_type]}</span><span>{kot.label}</span></div>
        <table className="t-items">
          <thead><tr><th className="l">Item</th><th>Qty</th></tr></thead>
          <tbody>{kot.kot_items.map((i, n) => (
            <tr key={n}><td className="l big">{i.name}{i.note && <div className="tiny">{i.note}</div>}</td><td className="big b">{qty(i.qty)}</td></tr>
          ))}</tbody>
        </table>
        <div className="c sep tiny">{kot.created_by}</div>
      </div>
    </div>
  )
}
