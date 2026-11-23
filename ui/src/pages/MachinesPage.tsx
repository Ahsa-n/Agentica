import React, { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../api/client'

interface Machine {
  id: string; type: string; host: string; port: number; user: string
  trusted: boolean; has_credentials: boolean
}

export default function MachinesPage() {
  const [machines, setMachines] = useState<Machine[]>([])
  const [credForm, setCredForm] = useState<Record<string, { username: string; password: string }>>({})
  const [trustForm, setTrustForm] = useState<Record<string, { fingerprint: string }>>({})
  const [testResult, setTestResult] = useState<Record<string, string>>({})

  const load = () => apiGet<Machine[]>('/api/machines').then(setMachines)
  useEffect(() => { load() }, [])

  const setCredentials = async (id: string) => {
    const f = credForm[id] || {}
    await apiPost(`/api/machines/${id}/credentials`, { username: f.username, password: f.password })
    await load()
  }

  const trust = async (id: string) => {
    const f = trustForm[id] || {}
    const m = machines.find(x => x.id === id)
    const body = m?.type === 'ssh'
      ? { fingerprint: f.fingerprint }
      : { thumbprint: f.fingerprint }
    await apiPost(`/api/machines/${id}/trust`, body)
    await load()
  }

  const testConn = async (id: string) => {
    setTestResult(prev => ({ ...prev, [id]: 'Testing…' }))
    const r = await apiPost<{ ok: boolean; message: string }>(`/api/machines/${id}/test`)
    setTestResult(prev => ({ ...prev, [id]: r.ok ? `✓ ${r.message}` : `✗ ${r.message}` }))
  }

  if (machines.length === 0) {
    return (
      <div style={{ padding: '2rem', color: '#888' }}>
        <h2 style={{ color: '#e5e5e5' }}>Machines</h2>
        <p>No targets configured. Add targets to <code>config/defaults/targets.yaml</code>.</p>
        <pre style={{ background: '#1a1a1a', padding: '1rem', borderRadius: 8, color: '#6ee7b7', fontSize: '0.8rem' }}>
{`targets:
  - id: linux-server-1
    type: ssh
    host: 192.168.1.10
    port: 22
    user: agentica
    trusted_fingerprint: null`}
        </pre>
      </div>
    )
  }

  return (
    <div style={{ padding: '2rem', maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h2 style={{ color: '#e5e5e5', margin: 0 }}>Machines</h2>
        <button onClick={load} style={{ background: '#1a1a1a', border: '1px solid #333', color: '#aaa', borderRadius: 6, padding: '0.4rem 0.8rem', cursor: 'pointer', fontSize: '0.8rem' }}>
          Reload
        </button>
      </div>

      {machines.map(m => (
        <div key={m.id} style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 8, padding: '1rem', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem' }}>
            <span style={{ color: '#e5e5e5', fontWeight: 600 }}>{m.id}</span>
            <span style={{ color: '#888', fontSize: '0.8rem' }}>{m.type.toUpperCase()} · {m.host}:{m.port}</span>
            <span style={{ color: m.trusted ? '#6ee7b7' : '#fca5a5', fontSize: '0.75rem', marginLeft: 'auto' }}>
              {m.trusted ? '✓ Trusted' : '✗ Untrusted'}
            </span>
            <span style={{ color: m.has_credentials ? '#6ee7b7' : '#fca5a5', fontSize: '0.75rem' }}>
              {m.has_credentials ? '✓ Credentials set' : '✗ No credentials'}
            </span>
          </div>

          {/* Credentials form */}
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
            <input
              placeholder="Username"
              value={credForm[m.id]?.username || ''}
              onChange={e => setCredForm(prev => ({ ...prev, [m.id]: { ...prev[m.id], username: e.target.value } }))}
              style={{ background: '#0f0f0f', border: '1px solid #333', borderRadius: 4, padding: '0.4rem 0.6rem', color: '#e5e5e5', fontSize: '0.8rem', width: 140 }}
            />
            <input
              type="password" placeholder="Password"
              value={credForm[m.id]?.password || ''}
              onChange={e => setCredForm(prev => ({ ...prev, [m.id]: { ...prev[m.id], password: e.target.value } }))}
              style={{ background: '#0f0f0f', border: '1px solid #333', borderRadius: 4, padding: '0.4rem 0.6rem', color: '#e5e5e5', fontSize: '0.8rem', width: 140 }}
            />
            <button onClick={() => setCredentials(m.id)} style={{ background: '#2a2a2a', color: '#aaa', border: '1px solid #333', borderRadius: 4, padding: '0.4rem 0.75rem', cursor: 'pointer', fontSize: '0.8rem' }}>
              Set Credentials
            </button>
          </div>

          {/* Trust form */}
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
            <input
              placeholder={m.type === 'ssh' ? 'SSH fingerprint (MD5)' : 'Certificate thumbprint'}
              value={trustForm[m.id]?.fingerprint || ''}
              onChange={e => setTrustForm(prev => ({ ...prev, [m.id]: { fingerprint: e.target.value } }))}
              style={{ background: '#0f0f0f', border: '1px solid #333', borderRadius: 4, padding: '0.4rem 0.6rem', color: '#e5e5e5', fontSize: '0.8rem', flex: 1 }}
            />
            <button onClick={() => trust(m.id)} style={{ background: '#2a2a2a', color: '#aaa', border: '1px solid #333', borderRadius: 4, padding: '0.4rem 0.75rem', cursor: 'pointer', fontSize: '0.8rem' }}>
              Trust
            </button>
            <button onClick={() => testConn(m.id)} style={{ background: '#14532d', color: '#6ee7b7', border: 'none', borderRadius: 4, padding: '0.4rem 0.75rem', cursor: 'pointer', fontSize: '0.8rem' }}>
              Test Connection
            </button>
          </div>

          {testResult[m.id] && (
            <div style={{ fontSize: '0.78rem', color: testResult[m.id].startsWith('✓') ? '#6ee7b7' : '#fca5a5', marginTop: '0.3rem' }}>
              {testResult[m.id]}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
