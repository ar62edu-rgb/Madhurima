import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'
import { DataTable, ErrorBox, Loading, Page, PeriodFilter, useApp, useLoad } from '../components/ui'
import { fmtDate, presetRange } from '../utils'

export default function Reports() {
  const [sp, setSp] = useSearchParams()
  const { toast } = useApp()
  const cat = useLoad(() => api.get('/api/reports'), [])
  const name = sp.get('r') || 'daily_sales'
  const [range, setRange] = useState(presetRange('month'))
  const meta = (cat.data || []).find(r => r.name === name)
  const { data, error, loading } = useLoad(() => api.get(`/api/reports/${name}` + qs({ from_date: range[0], to_date: range[1] })), [name, range[0], range[1]])
  const groups = {}
  ;(cat.data || []).forEach(r => { (groups[r.group] ||= []).push(r) })

  useEffect(() => { document.title = meta ? `${meta.title} – Reports` : 'Reports' }, [meta])

  async function exp(format) {
    try { await api.download(`/api/reports/${name}` + qs({ from_date: range[0], to_date: range[1], format }), `${name}.${format}`) }
    catch (e) { toast(e.message, 'error') }
  }

  return (
    <Page title="Reports" subtitle="Exportable to Excel and PDF. GST reports are prepared for GSTR-1 / GSTR-3B reconciliation — filing is done on the GST portal.">
      <div className="reports-layout">
        <aside className="report-list">
          {Object.entries(groups).map(([g, list]) => (
            <div key={g}>
              <div className="nav-section">{g}</div>
              {list.map(r => <button key={r.name} className={r.name === name ? 'active' : ''} onClick={() => setSp({ r: r.name })}>{r.title}</button>)}
            </div>
          ))}
        </aside>
        <section className="report-body">
          <div className="toolbar">
            <h2 className="grow">{data?.title || meta?.title}</h2>
            {meta?.dated !== false && <PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />}
            <button className="btn" onClick={() => exp('xlsx')}>⬇ Excel</button>
            <button className="btn" onClick={() => exp('pdf')}>⬇ PDF</button>
          </div>
          {data && <div className="muted">{data.dated ? `${fmtDate(data.from)} to ${fmtDate(data.to)}` : 'As on today'}{data.fy ? ` · FY ${data.fy}` : ''} · {data.rows.length} rows</div>}
          <ErrorBox error={error} />
          {loading && <Loading />}
          {data && <DataTable rows={data.rows} totals={Object.keys(data.totals).length ? data.totals : null}
            columns={data.columns.map(c => ({ ...c, type: c.type === 'date' ? 'text' : c.type }))} maxHeight="65vh" />}
          {data?.notes?.map((n, i) => <div key={i} className="note">ℹ {n}</div>)}
        </section>
      </div>
    </Page>
  )
}
