import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, qs } from '../api'
import { Card, ErrorBox, Loading, Page, PeriodFilter, Stat, useLoad } from '../components/ui'
import { compact, fmtDate, money, qty, today } from '../utils'

// Categorical slots (validated reference palette): 1 blue, 2 orange, 3 aqua.
const C1 = 'var(--series-1)', C2 = 'var(--series-2)', C3 = 'var(--series-3)'
const axis = { stroke: 'var(--muted)', fontSize: 11, tickLine: false, axisLine: false }
const tip = {
  contentStyle: { background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 },
  formatter: (v) => money(v),
}
const bar = { radius: [4, 4, 0, 0], maxBarSize: 28 }

export default function Dashboard() {
  const [range, setRange] = useState([today(), today()])
  const { data, error, loading } = useLoad(() => api.get('/api/dashboard' + qs({ from_date: range[0], to_date: range[1] })), [range[0], range[1]])
  const c = data?.cards
  const single = range[0] === range[1]
  const label = single ? (range[0] === today() ? "Today's" : fmtDate(range[0])) : 'Period'

  return (
    <Page title="Dashboard" subtitle={single ? fmtDate(range[0]) : `${fmtDate(range[0])} – ${fmtDate(range[1])}`}
          actions={<PeriodFilter from={range[0]} to={range[1]} onChange={(a, b) => setRange([a, b])} />}>
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {c && <>
        <div className="stats">
          <Stat label={`${label} total sales`} value={money(c.total_sales)} sub={`${c.total_bills} bills · avg ${money(c.average_bill)}`} tone="accent" />
          <Stat label="Cash sales" value={money(c.cash_sales)} />
          <Stat label="UPI sales" value={money(c.upi_sales)} />
          <Stat label="GST collected" value={money(c.gst_collected)} sub={`CGST ${money(c.cgst)} · SGST ${money(c.sgst)}${c.igst ? ' · IGST ' + money(c.igst) : ''}`} />
          <Stat label="Purchases" value={money(c.purchase_amount)} />
          <Stat label="Expenses" value={money(c.expenses)} />
          <Stat label="Profit estimate" value={money(c.profit_estimate)} sub="Sales ex-GST − food cost − expenses" tone={c.profit_estimate < 0 ? 'bad' : 'good'} />
          <Stat label="Current stock value" value={money(c.stock_value)} />
          <Stat label="Bills generated" value={c.total_bills} />
          <Stat label="Cancelled bills" value={c.cancelled_bills} tone={c.cancelled_bills ? 'warn' : ''} sub={c.credit_notes ? `Credit notes ${money(c.credit_notes)}` : ''} />
          <Stat label="Low stock alerts" value={c.low_stock_count} tone={c.low_stock_count ? 'warn' : ''} />
          <Stat label="Supplier outstanding" value={money(c.outstanding_supplier)} />
        </div>

        <div className="grid2">
          {data.daily.length > 1 && (
            <Card title="Daily sales">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={data.daily} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--grid)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={d => d.slice(8, 10) + '/' + d.slice(5, 7)} {...axis} />
                  <YAxis tickFormatter={compact} width={64} {...axis} />
                  <Tooltip {...tip} labelFormatter={fmtDate} />
                  <Line dataKey="sales" name="Sales" stroke={C1} strokeWidth={2} dot={data.daily.length < 40 ? { r: 3 } : false} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}
          <Card title="Monthly sales (last 12 months)">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="month" {...axis} />
                <YAxis tickFormatter={compact} width={64} {...axis} />
                <Tooltip {...tip} cursor={{ fill: 'var(--hover)' }} />
                <Bar dataKey="sales" name="Sales" fill={C1} {...bar} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card title="Cash vs UPI (monthly)">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="month" {...axis} />
                <YAxis tickFormatter={compact} width={64} {...axis} />
                <Tooltip {...tip} cursor={{ fill: 'var(--hover)' }} />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="cash" name="Cash" stackId="p" fill={C1} stroke="var(--surface)" strokeWidth={1} maxBarSize={28} />
                <Bar dataKey="upi" name="UPI" stackId="p" fill={C2} stroke="var(--surface)" strokeWidth={1} radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
            <div className="split-line">
              <span>Selected period: Cash <b>{money(c.cash_sales)}</b></span>
              <span>UPI <b>{money(c.upi_sales)}</b></span>
            </div>
          </Card>
          <Card title="Purchase vs sales (monthly)">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="month" {...axis} />
                <YAxis tickFormatter={compact} width={64} {...axis} />
                <Tooltip {...tip} cursor={{ fill: 'var(--hover)' }} />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="sales" name="Sales" fill={C1} {...bar} />
                <Bar dataKey="purchases" name="Purchases" fill={C2} {...bar} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card title="GST collected (monthly)">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="month" {...axis} />
                <YAxis tickFormatter={compact} width={64} {...axis} />
                <Tooltip {...tip} cursor={{ fill: 'var(--hover)' }} />
                <Bar dataKey="gst" name="GST" fill={C3} {...bar} />
              </BarChart>
            </ResponsiveContainer>
            <div className="split-line">
              {data.gst_split.map(g => <span key={g.name}>{g.name} <b>{money(g.value)}</b></span>)}
            </div>
          </Card>
          <Card title="Monthly expenses">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="month" {...axis} />
                <YAxis tickFormatter={compact} width={64} {...axis} />
                <Tooltip {...tip} cursor={{ fill: 'var(--hover)' }} />
                <Bar dataKey="expenses" name="Expenses" fill={C2} {...bar} />
              </BarChart>
            </ResponsiveContainer>
            {data.expense_by_category.length > 0 && (
              <div className="split-line wrap">
                {data.expense_by_category.slice(0, 6).map(e => <span key={e.name}>{e.name} <b>{money(e.value)}</b></span>)}
              </div>
            )}
          </Card>
          <Card title="Top selling items">
            {data.top_items.length ? (
              <ResponsiveContainer width="100%" height={Math.max(160, data.top_items.length * 30)}>
                <BarChart data={data.top_items} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--grid)" horizontal={false} />
                  <XAxis type="number" tickFormatter={compact} {...axis} />
                  <YAxis type="category" dataKey="name" width={130} {...axis} />
                  <Tooltip {...tip} cursor={{ fill: 'var(--hover)' }}
                           formatter={(v, n, p) => [`${money(v)} (${qty(p.payload.qty)} sold)`, 'Sales']} />
                  <Bar dataKey="amount" fill={C1} radius={[0, 4, 4, 0]} maxBarSize={18} />
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="empty">No sales in this period</div>}
          </Card>
          <Card title="Low stock items" actions={<Link to="/stock" className="btn small">Open stock</Link>}>
            {data.low_stock.length ? (
              <table className="table compact">
                <thead><tr><th>Item</th><th className="r">Stock</th><th className="r">Minimum</th></tr></thead>
                <tbody>{data.low_stock.map(p => (
                  <tr key={p.id}><td>⚠ {p.name}</td><td className="r">{qty(p.stock)} {p.unit}</td><td className="r">{qty(p.min)}</td></tr>
                ))}</tbody>
              </table>
            ) : <div className="empty">✓ All stock above minimum level</div>}
          </Card>
        </div>
      </>}
    </Page>
  )
}
