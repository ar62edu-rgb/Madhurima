import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, qs } from '../api'
import { Card, DataTable, Page, PeriodFilter, Stat, Tabs, sumBy, useApp, useLoad } from '../components/ui'
import { money, presetRange } from '../utils'

const QUICK = [
  ['gstr1_summary', 'GSTR-1 summary'], ['gstr3b_summary', 'GSTR-3B summary'], ['b2b_sales', 'B2B sales'], ['b2c_sales', 'B2C small'],
  ['b2cl_sales', 'B2C large'], ['hsn_summary', 'HSN/SAC summary'], ['sales_gst_register', 'Sales GST register'],
  ['purchase_gst_register', 'Purchase GST register'], ['output_gst_summary', 'Output GST'], ['input_gst_summary', 'Input GST'],
  ['cgst_summary', 'CGST'], ['sgst_summary', 'SGST'], ['igst_summary', 'IGST'], ['taxable_sales', 'Taxable sales'],
  ['exempt_sales', 'Exempt sales'], ['credit_note_register', 'Credit notes'], ['debit_note_register', 'Debit notes'],
  ['gst_monthly_summary', 'Monthly summary'], ['fy_gst_summary', 'Financial-year summary'],
]

export default function GST() {
  const { settings } = useApp()
  const [tab, setTab] = useState('overview')
  const [range, setRange] = useState(presetRange('month'))
  const sum = useLoad(() => api.get('/api/reports/gst_monthly_summary' + qs({ from_date: range[0], to_date: range[1] })), [range[0], range[1]])
  const t = sum.data?.totals || {}
  return (
    <Page title="GST Management" subtitle="Configuration, output/input tax, credit & debit notes and return-preparation reports"
          actions={<PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />}>
      <Tabs value={tab} onChange={setTab} tabs={[['overview', 'Overview'], ['credit', 'Credit notes'], ['debit', 'Debit notes']]} />
      {tab === 'overview' && <>
        <div className="stats">
          <Stat label="Taxable sales" value={money(t.taxable_sales)} />
          <Stat label="Exempt sales" value={money(t.exempt_sales)} />
          <Stat label="Output CGST" value={money(t.out_cgst)} />
          <Stat label="Output SGST" value={money(t.out_sgst)} />
          <Stat label="Output IGST" value={money(t.out_igst)} />
          <Stat label="Total output GST" value={money(t.total_output)} tone="accent" />
          <Stat label="Input GST (purchases)" value={money(t.total_input)} sub="Check ITC eligibility" />
        </div>
        <div className="grid2">
          <Card title="GST configuration" actions={<Link className="btn small" to="/settings">Edit in Settings</Link>}>
            <div className="kv-list">
              <div><span>GSTIN</span><b>{settings.gstin || 'Not set'}</b></div>
              <div><span>State / code</span><b>{settings.state} ({settings.state_code})</b></div>
              <div><span>Registration type</span><b>{settings.gst_registration_type}</b></div>
              <div><span>Invoice series</span><b>{settings.bill_prefix}/YY-YY/00001</b></div>
              <div><span>Default GST rate</span><b>{settings.default_gst_rate}%</b></div>
              <div><span>Default HSN/SAC</span><b>{settings.default_hsn}</b></div>
              <div><span>Menu prices</span><b>{settings.prices_include_gst === 'true' ? 'Inclusive of GST' : 'Exclusive (GST added)'}</b></div>
            </div>
            <p className="muted small">Item-wise GST rate, HSN/SAC and taxable / exempt / nil / zero-rated status are set on each product.
              Intra-state supplies use CGST + SGST; inter-state (customer GSTIN or state differs) uses IGST.
              Restaurant GST treatment depends on the nature of supply — confirm rates with your tax consultant.</p>
          </Card>
          <Card title="GST reports (Excel / PDF)">
            <div className="quick-links">
              {QUICK.map(([k, l]) => <Link key={k} to={`/reports?r=${k}`} className="btn small">{l}</Link>)}
            </div>
            <p className="muted small">This application does not file GST returns. Export these reports, reconcile, and file on the official GST portal.</p>
          </Card>
        </div>
        <h3>Month-wise</h3>
        {sum.data && <DataTable rows={sum.data.rows} totals={sum.data.totals} columns={sum.data.columns} />}
      </>}
      {tab === 'credit' && <Notes type="CREDIT" range={range} />}
      {tab === 'debit' && <Notes type="DEBIT" range={range} />}
    </Page>
  )
}

function Notes({ type, range }) {
  const { data } = useLoad(() => api.get('/api/notes' + qs({ note_type: type, from_date: range[0], to_date: range[1] })), [type, range[0], range[1]])
  return (
    <>
      <p className="muted">{type === 'CREDIT' ? 'Credit notes are raised from a bill (Sales & Bills → open bill → Credit note).' : 'Debit notes are raised from a purchase (Purchases → open purchase → Purchase return).'}</p>
      <div className="stats"><Stat label="Notes" value={(data || []).length} /><Stat label="Taxable" value={money(sumBy(data, 'taxable'))} />
        <Stat label="GST" value={money(sumBy(data, 'cgst') + sumBy(data, 'sgst') + sumBy(data, 'igst'))} /><Stat label="Total" value={money(sumBy(data, 'total'))} tone="accent" /></div>
      <DataTable rows={data} columns={[{ key: 'note_no', label: 'Note no' }, { key: 'note_date', label: 'Date', type: 'date' },
        { key: 'ref_doc_no', label: type === 'CREDIT' ? 'Against bill' : 'Supplier invoice' }, { key: 'party_name', label: 'Party' },
        { key: 'party_gstin', label: 'GSTIN' }, { key: 'reason', label: 'Reason' }, { key: 'taxable', label: 'Taxable', type: 'money' },
        { key: 'cgst', label: 'CGST', type: 'money' }, { key: 'sgst', label: 'SGST', type: 'money' }, { key: 'igst', label: 'IGST', type: 'money' },
        { key: 'total', label: 'Total', type: 'money' }, { key: 'settlement_mode', label: 'Settled' }]} />
    </>
  )
}
