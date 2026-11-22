import { useEffect, useState } from 'react'
import { api } from '../api'
import { Check, Field, useApp } from '../components/ui'

export default function Login({ onLogin }) {
  const { toast } = useApp()
  const [needsSetup, setNeedsSetup] = useState(null)
  const [f, setF] = useState({ username: '', password: '', confirm: '', restaurant_name: 'Madhurima Family Restaurant', full_name: '', load_sample_data: true })
  const [busy, setBusy] = useState(false)
  const set = (k) => (v) => setF(s => ({ ...s, [k]: v }))

  useEffect(() => { api.get('/api/auth/status').then(s => setNeedsSetup(s.needs_setup)).catch(e => toast(e.message, 'error')) }, [toast])

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      if (needsSetup) {
        if (f.password !== f.confirm) throw new Error('Passwords do not match')
        const r = await api.post('/api/auth/setup', f)
        await onLogin(r.token, r.user)
      } else {
        const r = await api.post('/api/auth/login', { username: f.username, password: f.password })
        await onLogin(r.token, r.user)
      }
    } catch (err) { toast(err.message, 'error') } finally { setBusy(false) }
  }

  if (needsSetup === null) return null
  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="login-logo">🍛</div>
        <h2>{needsSetup ? 'Welcome! First-time setup' : 'Madhurima Family Restaurant'}</h2>
        <p className="muted">{needsSetup ? 'Create the administrator account for this restaurant.' : 'Sign in to continue'}</p>
        {needsSetup && <Field label="Restaurant name"><input value={f.restaurant_name} onChange={e => set('restaurant_name')(e.target.value)} required /></Field>}
        {needsSetup && <Field label="Your name"><input value={f.full_name} onChange={e => set('full_name')(e.target.value)} /></Field>}
        <Field label="Username"><input value={f.username} onChange={e => set('username')(e.target.value)} autoFocus required autoComplete="username" /></Field>
        <Field label="Password"><input type="password" value={f.password} onChange={e => set('password')(e.target.value)} required minLength={needsSetup ? 6 : 1} autoComplete={needsSetup ? 'new-password' : 'current-password'} /></Field>
        {needsSetup && <Field label="Confirm password"><input type="password" value={f.confirm} onChange={e => set('confirm')(e.target.value)} required autoComplete="new-password" /></Field>}
        {needsSetup && <Check label="Load a sample menu, raw materials and a biriyani recipe (you can edit or deactivate later)" checked={f.load_sample_data} onChange={set('load_sample_data')} />}
        <button className="btn primary block" disabled={busy}>{needsSetup ? 'Create account & start' : 'Sign in'}</button>
      </form>
    </div>
  )
}
