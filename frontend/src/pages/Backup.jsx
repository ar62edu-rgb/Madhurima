import { useState } from 'react'
import { api } from '../api'
import { Badge, Card, DataTable, Page, useApp, useLoad } from '../components/ui'
import { fmtDateTime } from '../utils'

export default function Backup() {
  const { toast, logout } = useApp()
  const { data, reload } = useLoad(() => api.get('/api/backups'), [])
  const [busy, setBusy] = useState(false)

  async function run(fn, ok) {
    setBusy(true)
    try { await fn(); if (ok) toast(ok) } catch (e) { toast(e.message, 'error') } finally { setBusy(false); reload() }
  }
  const restore = (name) => {
    if (!confirm(`Restore "${name}"?\n\nALL current data will be replaced by this backup. A safety backup of the current data is taken first.`)) return
    run(async () => { await api.post(`/api/backups/${encodeURIComponent(name)}/restore`); toast('Restored. Please log in again.'); setTimeout(logout, 1200) })
  }
  const upload = (e) => {
    const file = e.target.files[0]
    e.target.value = ''
    if (!file || !confirm(`Restore from "${file.name}"? ALL current data will be replaced (a safety backup is taken first).`)) return
    const fd = new FormData(); fd.append('file', file)
    run(async () => { await api.upload('/api/backups/upload-restore', fd); toast('Restored. Please log in again.'); setTimeout(logout, 1200) })
  }
  const kinds = { auto: ['Automatic', 'blue'], manual: ['Manual', 'green'], 'pre-restore': ['Before restore', 'amber'] }

  return (
    <Page title="Backup & Restore" subtitle="Automatic backup daily and on every day closing. Copy backups to a pen drive / another disk regularly.">
      <div className="grid2">
        <Card title="Take a backup">
          <p>Creates a .zip with all data (bills, stock, accounts, settings, users) and purchase invoice attachments.</p>
          <button className="btn primary" disabled={busy} onClick={() => run(() => api.post('/api/backups'), 'Backup created')}>💾 Backup now</button>
          {data && <p className="muted small">Server folder: <code>{data.folder}</code> (in Docker this is the <code>backups</code> folder next to docker-compose.yml)</p>}
        </Card>
        <Card title="Restore from a file">
          <p>Pick a <code>madhurima_*.zip</code> backup from this or another computer.</p>
          <label className={`btn danger ${busy ? 'disabled' : ''}`}>Choose backup file…<input type="file" accept=".zip" hidden onChange={upload} disabled={busy} /></label>
        </Card>
      </div>
      <h3>Available backups</h3>
      <DataTable rows={data?.backups} columns={[
        { key: 'name', label: 'File' }, { key: 'kind', label: 'Type', render: r => <Badge tone={kinds[r.kind]?.[1]}>{kinds[r.kind]?.[0] || r.kind}</Badge> },
        { key: 'created_at', label: 'Created', render: r => fmtDateTime(r.created_at) }, { key: 'size', label: 'Size', render: r => `${(r.size / 1024).toFixed(0)} KB` },
        { key: 'act', label: '', render: r => <div className="row gap">
          <button className="btn small" onClick={() => api.download(`/api/backups/${encodeURIComponent(r.name)}/download`, r.name)}>Download</button>
          <button className="btn small" disabled={busy} onClick={() => restore(r.name)}>Restore</button>
          <button className="btn small" disabled={busy} onClick={() => confirm(`Delete ${r.name}?`) && run(() => api.del(`/api/backups/${encodeURIComponent(r.name)}`), 'Deleted')}>Delete</button>
        </div> }]} />
    </Page>
  )
}
