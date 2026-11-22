import { api } from '../api'
import { Badge, DataTable, Page, useApp, useLoad } from '../components/ui'
import { fmtDate } from '../utils'

export default function FinancialYears() {
  const { user, toast } = useApp()
  const { data, reload } = useLoad(() => api.get('/api/financial-years'), [])
  const admin = user.role === 'admin'
  async function act(fy, what) {
    if (!confirm(`${what === 'close' ? 'Close' : 'Reopen'} financial year ${fy.name}?${what === 'close' ? ' No entries can be made in a closed year.' : ''}`)) return
    try { await api.post(`/api/financial-years/${fy.id}/${what}`); reload() } catch (e) { toast(e.message, 'error') }
  }
  async function addNext() {
    const last = (data || [])[0]
    const year = last ? Number(last.name.slice(0, 4)) + 1 : new Date().getFullYear()
    try { await api.post('/api/financial-years', { start_year: year }); reload() } catch (e) { toast(e.message, 'error') }
  }
  return (
    <Page title="Financial Years" subtitle="April to March. Bill, purchase and note numbers restart every financial year."
          actions={admin && <button className="btn" onClick={addNext}>+ Create next year</button>}>
      <DataTable rows={data} columns={[
        { key: 'name', label: 'Year', render: r => <>{r.name} {r.is_current && <Badge tone="green">Current</Badge>}</> },
        { key: 'start_date', label: 'From', render: r => fmtDate(r.start_date) }, { key: 'end_date', label: 'To', render: r => fmtDate(r.end_date) },
        { key: 'bill_seq', label: 'Bills issued', type: 'num' }, { key: 'purchase_seq', label: 'Purchases', type: 'num' },
        { key: 'credit_note_seq', label: 'Credit notes', type: 'num' }, { key: 'debit_note_seq', label: 'Debit notes', type: 'num' },
        { key: 'is_closed', label: 'Status', render: r => r.is_closed ? <Badge tone="red">Closed</Badge> : <Badge tone="green">Open</Badge> },
        { key: 'act', label: '', render: r => admin && (r.is_closed
          ? <button className="btn small" onClick={() => act(r, 'reopen')}>Reopen</button>
          : !r.is_current && <button className="btn small" onClick={() => act(r, 'close')}>Close year</button>) },
      ]} />
      <p className="muted">Tip: use Reports → GST → "Financial Year GST Summary" and the Profit & Loss estimate with the FY preset for year-end figures.</p>
    </Page>
  )
}
