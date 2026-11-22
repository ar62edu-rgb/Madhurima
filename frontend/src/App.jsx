import { useCallback, useEffect, useMemo, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'
import { AppCtx, ToastHost, useToasts } from './components/ui'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import POS from './pages/POS'
import Bills from './pages/Bills'
import Purchases from './pages/Purchases'
import Stock from './pages/Stock'
import Products from './pages/Products'
import Customers from './pages/Customers'
import Suppliers from './pages/Suppliers'
import CashUpi from './pages/CashUpi'
import Expenses from './pages/Expenses'
import GST from './pages/GST'
import Closing from './pages/Closing'
import FinancialYears from './pages/FinancialYears'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Backup from './pages/Backup'
import { PrintBill, PrintKot } from './pages/Print'

const ALL = ['admin', 'manager', 'cashier']
const MGR = ['admin', 'manager']
export const NAV = [
  { section: 'Daily' },
  { to: '/', label: 'Dashboard', icon: '📊', roles: ALL, end: true },
  { to: '/pos', label: 'POS Billing', icon: '🧾', roles: ALL },
  { to: '/bills', label: 'Sales & Bills', icon: '📜', roles: ALL },
  { to: '/cash', label: 'Cash & UPI', icon: '💵', roles: ALL },
  { to: '/expenses', label: 'Expenses', icon: '💸', roles: ALL },
  { to: '/closing', label: 'Day / Month Closing', icon: '🔒', roles: MGR },
  { section: 'Inventory' },
  { to: '/purchases', label: 'Purchases', icon: '🛒', roles: MGR },
  { to: '/stock', label: 'Stock & Movement', icon: '📦', roles: MGR },
  { to: '/products', label: 'Products & Menu', icon: '🍛', roles: MGR },
  { section: 'Parties' },
  { to: '/customers', label: 'Customers', icon: '👥', roles: ALL },
  { to: '/suppliers', label: 'Suppliers', icon: '🚚', roles: MGR },
  { section: 'Accounts' },
  { to: '/gst', label: 'GST', icon: '🏛️', roles: MGR },
  { to: '/reports', label: 'Reports', icon: '📈', roles: MGR },
  { to: '/financial-years', label: 'Financial Years', icon: '📅', roles: MGR },
  { section: 'System' },
  { to: '/settings', label: 'Settings', icon: '⚙️', roles: ['admin'] },
  { to: '/backup', label: 'Backup & Restore', icon: '💾', roles: ['admin'] },
]

export default function App() {
  const [user, setUser] = useState(null)
  const [settings, setSettings] = useState(null)
  const [ready, setReady] = useState(false)
  const [toasts, toast] = useToasts()
  const location = useLocation()

  const logout = useCallback(() => { setToken(null); setUser(null) }, [])
  useEffect(() => setUnauthorizedHandler(logout), [logout])

  const loadSettings = useCallback(async () => setSettings(await api.get('/api/settings')), [])

  useEffect(() => {
    (async () => {
      if (getToken()) {
        try { setUser(await api.get('/api/auth/me')); await loadSettings() } catch { setToken(null) }
      }
      setReady(true)
    })()
  }, [loadSettings])

  const onLogin = useCallback(async (token, u) => {
    setToken(token); setUser(u); await loadSettings()
  }, [loadSettings])

  const ctx = useMemo(() => ({ user, settings, reloadSettings: loadSettings, toast, logout }),
    [user, settings, loadSettings, toast, logout])

  if (!ready) return null
  if (!user) return <AppCtx.Provider value={ctx}><Login onLogin={onLogin} /><ToastHost toasts={toasts} /></AppCtx.Provider>

  if (location.pathname.startsWith('/print/')) {
    return (
      <AppCtx.Provider value={ctx}>
        <Routes>
          <Route path="/print/bill/:id" element={<PrintBill />} />
          <Route path="/print/kot" element={<PrintKot />} />
        </Routes>
      </AppCtx.Provider>
    )
  }

  const allowed = (path) => NAV.find(n => n.to === path)?.roles.includes(user.role)
  const guard = (path, el) => allowed(path) ? el : <Navigate to="/pos" replace />

  return (
    <AppCtx.Provider value={ctx}>
      <div className={`shell ${location.pathname === '/pos' ? 'pos-mode' : ''}`}>
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-logo">🍛</div>
            <div>
              <div className="brand-name">{settings?.restaurant_name || 'Madhurima'}</div>
              <div className="brand-sub">Billing · GST · Inventory</div>
            </div>
          </div>
          <nav>
            {NAV.map((n, i) => n.section
              ? <div key={i} className="nav-section">{n.section}</div>
              : n.roles.includes(user.role) && (
                <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                  <span className="nav-icon">{n.icon}</span>{n.label}
                </NavLink>
              ))}
          </nav>
          <div className="sidebar-foot">
            <div><b>{user.full_name || user.username}</b></div>
            <div className="muted small">{user.role}</div>
            <button className="btn small" onClick={logout}>Log out</button>
          </div>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={guard('/', <Dashboard />)} />
            <Route path="/pos" element={<POS />} />
            <Route path="/bills" element={guard('/bills', <Bills />)} />
            <Route path="/purchases" element={guard('/purchases', <Purchases />)} />
            <Route path="/stock" element={guard('/stock', <Stock />)} />
            <Route path="/products" element={guard('/products', <Products />)} />
            <Route path="/customers" element={guard('/customers', <Customers />)} />
            <Route path="/suppliers" element={guard('/suppliers', <Suppliers />)} />
            <Route path="/cash" element={guard('/cash', <CashUpi />)} />
            <Route path="/expenses" element={guard('/expenses', <Expenses />)} />
            <Route path="/gst" element={guard('/gst', <GST />)} />
            <Route path="/closing" element={guard('/closing', <Closing />)} />
            <Route path="/financial-years" element={guard('/financial-years', <FinancialYears />)} />
            <Route path="/reports" element={guard('/reports', <Reports />)} />
            <Route path="/settings" element={guard('/settings', <Settings />)} />
            <Route path="/backup" element={guard('/backup', <Backup />)} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      <ToastHost toasts={toasts} />
    </AppCtx.Provider>
  )
}
