const inr = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const inr0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export const money = (v) => '₹' + inr.format(Number(v || 0))
export const num2 = (v) => inr.format(Number(v || 0))
export const compact = (v) => {
  const n = Number(v || 0)
  if (Math.abs(n) >= 1e7) return '₹' + (n / 1e7).toFixed(2) + ' Cr'
  if (Math.abs(n) >= 1e5) return '₹' + (n / 1e5).toFixed(2) + ' L'
  return '₹' + inr0.format(n)
}
export const qty = (v) => Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 3 })

export function iso(d) {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
  return z.toISOString().slice(0, 10)
}
export const today = () => iso(new Date())

export function fmtDate(s) {
  if (!s) return ''
  const [y, m, d] = s.slice(0, 10).split('-')
  return `${d}-${m}-${y}`
}
export function fmtDateTime(s) {
  if (!s) return ''
  return `${fmtDate(s)} ${s.slice(11, 16)}`
}

export function fyStart(d = new Date()) {
  const y = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1
  return new Date(y, 3, 1)
}

/** Period presets used by dashboard and reports. */
export function presetRange(key) {
  const now = new Date()
  const y = now.getFullYear(), m = now.getMonth()
  switch (key) {
    case 'today': return [today(), today()]
    case 'yesterday': { const d = new Date(now); d.setDate(d.getDate() - 1); return [iso(d), iso(d)] }
    case 'week': { const d = new Date(now); d.setDate(d.getDate() - 6); return [iso(d), today()] }
    case 'month': return [iso(new Date(y, m, 1)), today()]
    case 'last_month': return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))]
    case 'quarter': {
      // Indian FY quarters: Apr-Jun, Jul-Sep, Oct-Dec, Jan-Mar
      const qStartMonth = Math.floor(((m + 9) % 12) / 3) * 3 // months since April
      const start = new Date(fyStart(now).getFullYear(), 3 + qStartMonth, 1)
      return [iso(start), today()]
    }
    case 'fy': return [iso(fyStart(now)), today()]
    case 'last_fy': { const s = fyStart(now); return [iso(new Date(s.getFullYear() - 1, 3, 1)), iso(new Date(s.getFullYear(), 2, 31))] }
    default: return [today(), today()]
  }
}

export const PRESETS = [
  ['today', 'Today'], ['yesterday', 'Yesterday'], ['week', 'Last 7 days'], ['month', 'This month'],
  ['last_month', 'Last month'], ['quarter', 'This quarter'], ['fy', 'This FY'], ['last_fy', 'Last FY'],
]

export const ORDER_TYPES = { DINE_IN: 'Dine-in', TAKEAWAY: 'Takeaway', DELIVERY: 'Delivery' }

export function amountInWords(amount) {
  const a = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve',
    'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
  const b = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
  const two = (n) => n < 20 ? a[n] : b[Math.floor(n / 10)] + (n % 10 ? ' ' + a[n % 10] : '')
  const three = (n) => (n >= 100 ? a[Math.floor(n / 100)] + ' Hundred' + (n % 100 ? ' ' : '') : '') + two(n % 100)
  let n = Math.floor(Math.abs(amount))
  const paise = Math.round((Math.abs(amount) - n) * 100)
  if (n === 0 && !paise) return 'Zero Rupees Only'
  const parts = []
  const crore = Math.floor(n / 1e7); n %= 1e7
  const lakh = Math.floor(n / 1e5); n %= 1e5
  const thousand = Math.floor(n / 1000); n %= 1000
  if (crore) parts.push(three(crore) + ' Crore')
  if (lakh) parts.push(two(lakh) + ' Lakh')
  if (thousand) parts.push(two(thousand) + ' Thousand')
  if (n) parts.push(three(n))
  let s = parts.join(' ') + ' Rupees'
  if (paise) s += ' and ' + two(paise) + ' Paise'
  return s + ' Only'
}
