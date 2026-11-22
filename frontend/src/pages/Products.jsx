import { useEffect, useState } from 'react'
import { api, qs } from '../api'
import { Badge, Check, DataTable, ErrorBox, Field, Modal, Page, Select, Tabs, useApp, useLoad } from '../components/ui'
import { money, qty } from '../utils'

const TYPES = [['MENU', 'Menu item (sold)'], ['RAW', 'Raw material'], ['PACKING', 'Packing material'], ['OTHER', 'Other (sold)']]
const TAX = [['TAXABLE', 'Taxable'], ['EXEMPT', 'Exempt'], ['NIL', 'Nil rated'], ['ZERO', 'Zero rated']]
const UNITS = ['NOS', 'PLATE', 'CUP', 'GLASS', 'BTL', 'PKT', 'KG', 'GM', 'LTR', 'ML', 'BOX', 'DOZ']

export default function Products() {
  const [tab, setTab] = useState('products')
  return (
    <Page title="Products & Menu" subtitle="Menu items, raw materials, categories and recipes">
      <Tabs value={tab} onChange={setTab} tabs={[['products', 'Products'], ['categories', 'Categories']]} />
      {tab === 'products' ? <ProductList /> : <Categories />}
    </Page>
  )
}

function ProductList() {
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [cat, setCat] = useState('')
  const [edit, setEdit] = useState(null)
  const cats = useLoad(() => api.get('/api/categories'), [])
  const { data, error, reload } = useLoad(() => api.get('/api/products' + qs({ q, product_type: type, category_id: cat })), [q, type, cat])
  return (
    <>
      <div className="toolbar">
        <input placeholder="Search name / code" value={q} onChange={e => setQ(e.target.value)} />
        <Select value={type} onChange={setType} placeholder="All types" options={TYPES} />
        <Select value={cat} onChange={setCat} placeholder="All categories" options={(cats.data || []).map(c => [c.id, c.name])} />
        <button className="btn primary" onClick={() => setEdit({})}>+ New product</button>
      </div>
      <ErrorBox error={error} />
      <DataTable rows={data} onRowClick={r => setEdit(r)} rowClass={r => r.is_active ? '' : 'cancelled'} columns={[
        { key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }, { key: 'category_name', label: 'Category' },
        { key: 'product_type', label: 'Type' }, { key: 'hsn', label: 'HSN/SAC' }, { key: 'unit', label: 'Unit' },
        { key: 'selling_price', label: 'Selling', type: 'money' }, { key: 'purchase_price', label: 'Cost', type: 'money' },
        { key: 'gst_rate', label: 'GST', render: r => r.tax_category === 'TAXABLE' ? `${r.gst_rate}%` : r.tax_category },
        { key: 'current_stock', label: 'Stock', type: 'num', render: r => r.track_stock ? <>{qty(r.current_stock)} {r.low_stock && <Badge tone="red">Low</Badge>}</> : (r.use_recipe ? <Badge tone="blue">Recipe</Badge> : '—') },
        { key: 'is_active', label: 'Active', render: r => r.is_active ? 'Yes' : <Badge tone="grey">Inactive</Badge> },
      ]} />
      {edit && <ProductForm product={edit} categories={cats.data || []} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload() }} />}
    </>
  )
}

function ProductForm({ product, categories, onClose, onSaved }) {
  const { settings, toast } = useApp()
  const isNew = !product.id
  const [f, setF] = useState(() => isNew ? {
    code: '', name: '', category_id: '', subcategory: '', product_type: 'MENU', hsn: settings.default_hsn, unit: 'NOS',
    purchase_price: 0, selling_price: 0, gst_rate: Number(settings.default_gst_rate || 5), tax_category: 'TAXABLE',
    opening_stock: 0, min_stock: 0, max_stock: 0, track_stock: false, use_recipe: false, is_active: true,
  } : { ...product, category_id: product.category_id || '' })
  const [recipe, setRecipe] = useState([])
  const [ingredients, setIngredients] = useState([])
  const set = (k) => (v) => setF(s => ({ ...s, [k]: v }))

  useEffect(() => {
    if (isNew) api.get('/api/products/next-code?product_type=' + f.product_type).then(r => setF(s => s.code ? s : { ...s, code: r.code }))
    else api.get(`/api/products/${product.id}`).then(p => setRecipe(p.recipe))
    api.get('/api/products?product_type=RAW,PACKING&active_only=true').then(setIngredients)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function save() {
    const body = { ...f, category_id: f.category_id ? Number(f.category_id) : null }
    for (const k of ['purchase_price', 'selling_price', 'gst_rate', 'opening_stock', 'min_stock', 'max_stock']) body[k] = Number(body[k]) || 0
    try {
      const saved = isNew ? await api.post('/api/products', body) : await api.put(`/api/products/${product.id}`, body)
      if (f.product_type === 'MENU' || f.product_type === 'OTHER') {
        if (recipe.length || product.use_recipe) {
          await api.put(`/api/products/${saved.id}/recipe`, recipe.filter(r => r.ingredient_id && Number(r.quantity) > 0)
            .map(r => ({ ingredient_id: Number(r.ingredient_id), quantity: Number(r.quantity) })))
        }
      }
      toast('Product saved')
      onSaved()
    } catch (e) { toast(e.message, 'error') }
  }

  const sold = f.product_type === 'MENU' || f.product_type === 'OTHER'
  const recipeCost = recipe.reduce((s, r) => s + (Number(r.quantity) || 0) * (ingredients.find(i => i.id === Number(r.ingredient_id))?.purchase_price || 0), 0)

  return (
    <Modal wide title={isNew ? 'New product' : `Edit ${product.name}`} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" onClick={save} disabled={!f.name || !f.code}>Save</button>
    </>}>
      <div className="form-grid three">
        <Field label="Product ID / code"><input value={f.code} onChange={e => set('code')(e.target.value)} /></Field>
        <Field label="Name" span={2}><input value={f.name} onChange={e => set('name')(e.target.value)} autoFocus /></Field>
        <Field label="Type"><Select value={f.product_type} onChange={set('product_type')} options={TYPES} /></Field>
        <Field label="Category"><Select value={f.category_id} onChange={set('category_id')} placeholder="—" options={categories.map(c => [c.id, c.name])} /></Field>
        <Field label="Subcategory"><input value={f.subcategory} onChange={e => set('subcategory')(e.target.value)} /></Field>
        <Field label="HSN / SAC code" hint="Restaurant service SAC is usually 996331"><input value={f.hsn} onChange={e => set('hsn')(e.target.value)} /></Field>
        <Field label="Unit"><Select value={f.unit} onChange={set('unit')} options={UNITS} /></Field>
        <Field label="Tax category"><Select value={f.tax_category} onChange={set('tax_category')} options={TAX} /></Field>
        <Field label="GST rate %"><Select value={String(f.gst_rate)} onChange={v => set('gst_rate')(Number(v))} options={['0', '0.25', '3', '5', '12', '18', '28', '40'].map(x => [x, x + '%'])} /></Field>
        <Field label="Selling price ₹"><input value={f.selling_price} onChange={e => set('selling_price')(e.target.value)} inputMode="decimal" /></Field>
        <Field label="Purchase / cost price ₹"><input value={f.purchase_price} onChange={e => set('purchase_price')(e.target.value)} inputMode="decimal" /></Field>
        {isNew && <Field label="Opening stock"><input value={f.opening_stock} onChange={e => set('opening_stock')(e.target.value)} inputMode="decimal" /></Field>}
        {!isNew && <Field label="Current stock"><input value={`${qty(f.current_stock)} ${f.unit}`} disabled /></Field>}
        <Field label="Minimum stock level"><input value={f.min_stock} onChange={e => set('min_stock')(e.target.value)} inputMode="decimal" /></Field>
        <Field label="Maximum stock level"><input value={f.max_stock} onChange={e => set('max_stock')(e.target.value)} inputMode="decimal" /></Field>
      </div>
      <div className="row gap wrap">
        <Check label="Track stock for this item" checked={f.track_stock} onChange={set('track_stock')} />
        <Check label="Active" checked={f.is_active} onChange={set('is_active')} />
      </div>
      {sold && (
        <div className="recipe">
          <h4>Recipe (stock deducted from ingredients on every sale)</h4>
          {recipe.map((r, i) => (
            <div className="row gap" key={i}>
              <select value={r.ingredient_id} onChange={e => setRecipe(x => x.map((y, j) => j === i ? { ...y, ingredient_id: e.target.value } : y))}>
                <option value="">Select ingredient</option>
                {ingredients.map(p => <option key={p.id} value={p.id}>{p.name} ({p.unit})</option>)}
              </select>
              <input className="narrow" placeholder="Qty" value={r.quantity} onChange={e => setRecipe(x => x.map((y, j) => j === i ? { ...y, quantity: e.target.value } : y))} />
              <span className="muted">{ingredients.find(p => p.id === Number(r.ingredient_id))?.unit} per 1 {f.unit}</span>
              <button className="icon-btn" onClick={() => setRecipe(x => x.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <div className="row gap">
            <button className="btn small" onClick={() => setRecipe(x => [...x, { ingredient_id: '', quantity: '' }])}>+ Ingredient</button>
            {recipe.length > 0 && <span className="muted">Estimated food cost per {f.unit}: <b>{money(recipeCost)}</b>
              {Number(f.selling_price) > 0 && <> · food cost {Math.round(recipeCost * 100 / Number(f.selling_price))}%</>}</span>}
          </div>
        </div>
      )}
    </Modal>
  )
}

function Categories() {
  const { toast } = useApp()
  const { data, reload } = useLoad(() => api.get('/api/categories'), [])
  const [edit, setEdit] = useState(null)
  async function save() {
    const body = { ...edit, parent_id: edit.parent_id ? Number(edit.parent_id) : null, sort_order: Number(edit.sort_order) || 0 }
    try { edit.id ? await api.put(`/api/categories/${edit.id}`, body) : await api.post('/api/categories', body); setEdit(null); reload() }
    catch (e) { toast(e.message, 'error') }
  }
  const names = Object.fromEntries((data || []).map(c => [c.id, c.name]))
  return (
    <>
      <div className="toolbar"><button className="btn primary" onClick={() => setEdit({ name: '', parent_id: '', show_in_pos: true, sort_order: 0, is_active: true })}>+ New category</button></div>
      <DataTable rows={data} onRowClick={setEdit} columns={[
        { key: 'name', label: 'Name' }, { key: 'parent_id', label: 'Parent', render: r => names[r.parent_id] || '—' },
        { key: 'show_in_pos', label: 'Show in POS' }, { key: 'sort_order', label: 'Order', type: 'num' }, { key: 'is_active', label: 'Active' }]} />
      {edit && (
        <Modal title={edit.id ? 'Edit category' : 'New category'} onClose={() => setEdit(null)} footer={<button className="btn primary" onClick={save}>Save</button>}>
          <Field label="Name"><input value={edit.name} onChange={e => setEdit({ ...edit, name: e.target.value })} autoFocus /></Field>
          <Field label="Parent category (makes this a subcategory)"><Select value={edit.parent_id || ''} onChange={v => setEdit({ ...edit, parent_id: v })} placeholder="—" options={(data || []).filter(c => c.id !== edit.id).map(c => [c.id, c.name])} /></Field>
          <Field label="Sort order"><input value={edit.sort_order} onChange={e => setEdit({ ...edit, sort_order: e.target.value })} /></Field>
          <Check label="Show in POS" checked={edit.show_in_pos} onChange={v => setEdit({ ...edit, show_in_pos: v })} />
          <Check label="Active" checked={edit.is_active} onChange={v => setEdit({ ...edit, is_active: v })} />
        </Modal>
      )}
    </>
  )
}
