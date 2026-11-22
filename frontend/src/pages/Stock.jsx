import { useState } from 'react'
import { api, qs } from '../api'
import { Badge, Check, DataTable, ErrorBox, Field, Modal, Page, PeriodFilter, Select, Stat, Tabs, sumBy, useApp, useLoad } from '../components/ui'
import { money, qty, today } from '../utils'

const ADJ = {
  ADD: [['ADDITION', 'Stock addition'], ['OPENING', 'Opening stock entry'], ['RETURN', 'Return (in)'], ['CORRECTION', 'Stock correction (+)'], ['MANUAL', 'Manual adjustment (+)']],
  REDUCE: [['WASTAGE', 'Wastage'], ['DAMAGE', 'Damaged stock'], ['EXPIRY', 'Expired stock'], ['REDUCTION', 'Stock reduction'], ['CORRECTION', 'Stock correction (−)'], ['MANUAL', 'Manual adjustment (−)']],
}

export default function Stock() {
  const [tab, setTab] = useState('current')
  return (
    <Page title="Stock & Movement" subtitle="Every stock change is recorded in the movement register (audit trail)">
      <Tabs value={tab} onChange={setTab} tabs={[['current', 'Current stock'], ['reconcile', 'Stock reconciliation'], ['movements', 'Movement register']]} />
      {tab === 'current' && <Current />}
      {tab === 'reconcile' && <Reconcile />}
      {tab === 'movements' && <Movements />}
    </Page>
  )
}

function Current() {
  const [lowOnly, setLowOnly] = useState(false)
  const [q, setQ] = useState('')
  const [adjust, setAdjust] = useState(null)
  const [history, setHistory] = useState(null)
  const { data, error, reload } = useLoad(() => api.get('/api/products' + qs({ q })), [q])
  const rows = (data || []).filter(p => p.track_stock && (!lowOnly || p.low_stock))
  return (
    <>
      <div className="stats">
        <Stat label="Tracked items" value={rows.length} />
        <Stat label="Stock value" value={money(sumBy(rows, 'stock_value'))} tone="accent" />
        <Stat label="Low stock" value={rows.filter(r => r.low_stock).length} tone="warn" />
      </div>
      <div className="toolbar">
        <input placeholder="Search product" value={q} onChange={e => setQ(e.target.value)} />
        <Check label="Low stock only" checked={lowOnly} onChange={setLowOnly} />
        <button className="btn primary" onClick={() => setAdjust({})}>+ Stock adjustment</button>
      </div>
      <ErrorBox error={error} />
      <DataTable rows={rows} onRowClick={setHistory} empty="No stock-tracked items. Enable 'Track stock' on products or enter a purchase."
        columns={[
          { key: 'code', label: 'Code' }, { key: 'name', label: 'Product' }, { key: 'category_name', label: 'Category' },
          { key: 'unit', label: 'Unit' }, { key: 'current_stock', label: 'Stock', type: 'num' },
          { key: 'min_stock', label: 'Min', type: 'num' }, { key: 'max_stock', label: 'Max', type: 'num' },
          { key: 'purchase_price', label: 'Cost', type: 'money' }, { key: 'stock_value', label: 'Value', type: 'money' },
          { key: 'low_stock', label: 'Status', render: r => r.low_stock ? <Badge tone="red">⚠ Low</Badge> : <Badge tone="green">OK</Badge> },
          { key: 'act', label: '', render: r => <button className="btn small" onClick={e => { e.stopPropagation(); setAdjust({ product_id: r.id }) }}>Adjust</button> },
        ]} />
      {adjust && <AdjustDialog initial={adjust} products={data || []} onClose={() => setAdjust(null)} onDone={() => { setAdjust(null); reload() }} />}
      {history && <HistoryDialog product={history} onClose={() => setHistory(null)} />}
    </>
  )
}

function AdjustDialog({ initial, products, onClose, onDone }) {
  const { toast } = useApp()
  const [f, setF] = useState({ product_id: initial.product_id || '', direction: 'REDUCE', movement_type: 'WASTAGE', qty: '', remarks: '', reference: '' })
  const p = products.find(x => x.id === Number(f.product_id))
  async function save() {
    try {
      await api.post('/api/stock/adjust', { ...f, product_id: Number(f.product_id), qty: Number(f.qty) })
      toast('Stock updated'); onDone()
    } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Modal title="Stock adjustment" onClose={onClose} footer={<button className="btn primary" onClick={save} disabled={!f.product_id || !(Number(f.qty) > 0)}>Save</button>}>
      <div className="form-grid">
        <Field label="Product" span={2}><Select value={f.product_id} onChange={v => setF({ ...f, product_id: v })} placeholder="Select" options={products.map(x => [x.id, `${x.name} (${qty(x.current_stock)} ${x.unit})`])} /></Field>
        <Field label="Direction"><Select value={f.direction} onChange={v => setF({ ...f, direction: v, movement_type: ADJ[v][0][0] })} options={[['ADD', 'Add stock'], ['REDUCE', 'Reduce stock']]} /></Field>
        <Field label="Type"><Select value={f.movement_type} onChange={v => setF({ ...f, movement_type: v })} options={ADJ[f.direction]} /></Field>
        <Field label={`Quantity ${p ? '(' + p.unit + ')' : ''}`}><input value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} inputMode="decimal" autoFocus /></Field>
        <Field label="Reference"><input value={f.reference} onChange={e => setF({ ...f, reference: e.target.value })} /></Field>
        <Field label="Remarks" span={2}><input value={f.remarks} onChange={e => setF({ ...f, remarks: e.target.value })} /></Field>
      </div>
      {p && <div className="muted">Current: {qty(p.current_stock)} {p.unit} → after: <b>{qty(p.current_stock + (f.direction === 'ADD' ? 1 : -1) * (Number(f.qty) || 0))}</b></div>}
    </Modal>
  )
}

function HistoryDialog({ product, onClose }) {
  const { data } = useLoad(() => api.get(`/api/stock/product/${product.id}`), [product.id])
  return (
    <Modal wide title={`Stock history — ${product.name}`} onClose={onClose}>
      <DataTable rows={data?.movements} maxHeight="60vh" columns={MOV_COLS.filter(c => c.key !== 'product_name')} />
    </Modal>
  )
}

const MOV_COLS = [
  { key: 'id', label: 'Txn ID' }, { key: 'created_at', label: 'Date / Time', type: 'datetime' },
  { key: 'product_name', label: 'Product' }, { key: 'movement_type', label: 'Type', render: r => <Badge tone={r.added_qty ? 'green' : 'red'}>{r.movement_type.replace('_', ' ')}</Badge> },
  { key: 'opening_qty', label: 'Opening', type: 'num' }, { key: 'added_qty', label: 'Added', type: 'num' },
  { key: 'reduced_qty', label: 'Reduced', type: 'num' }, { key: 'closing_qty', label: 'Closing', type: 'num' },
  { key: 'ref_no', label: 'Reference' }, { key: 'remarks', label: 'Remarks' }, { key: 'created_by', label: 'By' },
]

function Movements() {
  const [range, setRange] = useState([today(), today()])
  const [type, setType] = useState('')
  const [pid, setPid] = useState('')
  const types = useLoad(() => api.get('/api/stock/types'), [])
  const prods = useLoad(() => api.get('/api/products'), [])
  const { data, error } = useLoad(() => api.get('/api/stock/movements' + qs({ from_date: range[0], to_date: range[1], movement_type: type, product_id: pid })), [range[0], range[1], type, pid])
  return (
    <>
      <div className="toolbar">
        <PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />
        <Select value={type} onChange={setType} placeholder="All types" options={types.data || []} />
        <Select value={pid} onChange={setPid} placeholder="All products" options={(prods.data || []).filter(p => p.track_stock).map(p => [p.id, p.name])} />
      </div>
      <ErrorBox error={error} />
      <DataTable rows={data} columns={MOV_COLS} />
    </>
  )
}

function Reconcile() {
  const { toast } = useApp()
  const { data, reload } = useLoad(() => api.get('/api/products'), [])
  const [counts, setCounts] = useState({})
  const [result, setResult] = useState(null)
  const rows = (data || []).filter(p => p.track_stock && p.is_active)
  async function submit() {
    const list = Object.entries(counts).filter(([, v]) => v !== '').map(([k, v]) => ({ product_id: Number(k), physical_qty: Number(v) }))
    if (!list.length) return toast('Enter at least one physical count', 'error')
    if (!confirm(`Post ${list.length} physical count(s)? Differences will be adjusted as RECONCILIATION movements.`)) return
    try { setResult(await api.post('/api/stock/reconcile', { counts: list })); setCounts({}); reload(); toast('Stock reconciled') }
    catch (e) { toast(e.message, 'error') }
  }
  return (
    <>
      <p className="muted">Enter the physically counted quantity. Leave blank to skip an item. The system posts the difference.</p>
      <table className="table">
        <thead><tr><th>Product</th><th>Unit</th><th className="r">System stock</th><th className="r">Physical count</th><th className="r">Difference</th></tr></thead>
        <tbody>{rows.map(p => {
          const v = counts[p.id]
          const d = v === undefined || v === '' ? null : Number(v) - p.current_stock
          return (
            <tr key={p.id}><td>{p.name}</td><td>{p.unit}</td><td className="r">{qty(p.current_stock)}</td>
              <td className="r"><input className="narrow" value={v ?? ''} onChange={e => setCounts(s => ({ ...s, [p.id]: e.target.value }))} inputMode="decimal" /></td>
              <td className={`r ${d < 0 ? 'neg' : d > 0 ? 'pos' : ''}`}>{d === null ? '' : qty(d)}</td></tr>
          )
        })}</tbody>
      </table>
      <div className="toolbar"><button className="btn primary" onClick={submit}>Post reconciliation</button></div>
      {result && <DataTable rows={result} columns={[{ key: 'name', label: 'Product' }, { key: 'system_qty', label: 'System', type: 'num' },
        { key: 'physical_qty', label: 'Physical', type: 'num' }, { key: 'difference', label: 'Difference', type: 'num' }, { key: 'value_difference', label: 'Value diff', type: 'money' }]} />}
    </>
  )
}
