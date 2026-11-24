import React, { useEffect, useState } from 'react'
import {
  Server, Wifi, WifiOff, KeyRound, Shield, ShieldOff, TestTube2, ChevronDown, ChevronUp,
  Plus, Trash2, Fingerprint, MessageSquare,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { apiDelete, apiGet, apiPost } from '../api/client'

interface Machine {
  id: string; type: 'ssh' | 'winrm'; host: string; port: number; user: string
  trusted: boolean; trusted_value: string | null; has_credentials: boolean
}

interface FetchedFp { value: string; md5?: string; sha256?: string; sha1?: string; key_type?: string }

const emptyNew = { id: '', type: 'ssh' as 'ssh' | 'winrm', host: '', port: '', user: '' }

export default function MachinesPage() {
  const navigate = useNavigate()
  const [machines, setMachines] = useState<Machine[]>([])
  const [loaded, setLoaded] = useState(false)
  const [credForm, setCredForm] = useState<Record<string, { username: string; password: string; private_key: string }>>({})
  const [trustForm, setTrustForm] = useState<Record<string, string>>({})
  const [fetched, setFetched] = useState<Record<string, FetchedFp | { error: string }>>({})
  const [status, setStatus] = useState<Record<string, { ok: boolean; msg: string }>>({})
  const [expanded, setExpanded] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [newM, setNewM] = useState(emptyNew)
  const [addError, setAddError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = async () => {
    try { setMachines(await apiGet<Machine[]>('/api/machines')) } finally { setLoaded(true) }
  }
  useEffect(() => { load() }, [])

  const say = (id: string, ok: boolean, msg: string) => setStatus(p => ({ ...p, [id]: { ok, msg } }))
  const errMsg = (e: any) => {
    const m = String(e?.message || e)
    const json = m.indexOf('{')
    if (json >= 0) { try { return JSON.parse(m.slice(json)).detail || m } catch { /* raw */ } }
    return m
  }

  const add = async () => {
    setAddError(null)
    try {
      await apiPost('/api/machines', {
        id: newM.id.trim(), type: newM.type, host: newM.host.trim(),
        ...(newM.port ? { port: Number(newM.port) } : {}),
        ...(newM.user.trim() ? { user: newM.user.trim() } : {}),
      })
      const id = newM.id.trim()
      setNewM(emptyNew); setShowAdd(false)
      await load()
      setExpanded(id)
    } catch (e) { setAddError(errMsg(e)) }
  }

  const remove = async (id: string) => {
    if (!window.confirm(`Remove machine "${id}" and its stored credentials?`)) return
    await apiDelete(`/api/machines/${id}`)
    await load()
  }

  const saveCreds = async (m: Machine) => {
    const f = credForm[m.id] || { username: '', password: '', private_key: '' }
    if (!f.password && !f.private_key && !f.username) { say(m.id, false, 'Enter a password or private key'); return }
    try {
      await apiPost(`/api/machines/${m.id}/credentials`, {
        ...(f.username ? { username: f.username } : {}),
        ...(f.password ? { password: f.password } : {}),
        ...(f.private_key ? { private_key: f.private_key } : {}),
      })
      setCredForm(p => ({ ...p, [m.id]: { username: '', password: '', private_key: '' } }))
      say(m.id, true, 'Credentials saved to the OS keyring')
      await load()
    } catch (e) { say(m.id, false, errMsg(e)) }
  }

  const fetchFp = async (m: Machine) => {
    setBusy(m.id + ':fp')
    try {
      const r = await apiGet<FetchedFp>(`/api/machines/${m.id}/fingerprint`)
      setFetched(p => ({ ...p, [m.id]: r }))
      setTrustForm(p => ({ ...p, [m.id]: r.value }))
    } catch (e) {
      setFetched(p => ({ ...p, [m.id]: { error: errMsg(e) } }))
    } finally { setBusy(null) }
  }

  const trust = async (m: Machine) => {
    const value = (trustForm[m.id] || '').trim()
    if (!value) { say(m.id, false, 'Fetch or paste a fingerprint first'); return }
    try {
      await apiPost(`/api/machines/${m.id}/trust`, m.type === 'ssh' ? { fingerprint: value } : { thumbprint: value })
      say(m.id, true, 'Trusted')
      await load()
    } catch (e) { say(m.id, false, errMsg(e)) }
  }

  const untrust = async (m: Machine) => {
    await apiDelete(`/api/machines/${m.id}/trust`)
    await load()
  }

  const testConn = async (m: Machine) => {
    setBusy(m.id + ':test')
    say(m.id, true, 'Testing…')
    try {
      const r = await apiPost<{ ok: boolean; message: string }>(`/api/machines/${m.id}/test`)
      say(m.id, r.ok, r.message)
    } catch (e) { say(m.id, false, errMsg(e)) } finally { setBusy(null) }
  }

  const askAgent = async (m: Machine) => {
    const { id } = await apiPost<{ id: string }>('/api/sessions')
    navigate(`/chat/${id}`, {
      state: {
        forceCategories: ['remote', 'monitoring', 'services'],
        examples: [
          `What is the CPU and memory usage on ${m.id}?`,
          `Show disk usage on ${m.id}`,
          `Is nginx running on ${m.id}?`,
          `Check application status on ${m.id}`,
        ],
      },
    })
  }

  return (
    <div className="page-pad" style={{ maxWidth: 820, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', gap: '0.5rem', flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ color: '#fff', margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>Machines</h2>
          <p style={{ margin: '0.25rem 0 0', color: '#555', fontSize: '0.8rem' }}>
            Remote Linux (SSH) and Windows (WinRM HTTPS) servers the agent can manage. Agentless — nothing is installed on them.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={load} style={btnGhost}>Reload</button>
          <button onClick={() => setShowAdd(s => !s)} style={btnSmall('#0f2a1f', '#6ee7b7', '#166534')}>
            <Plus size={13} strokeWidth={2.5} /> Add machine
          </button>
        </div>
      </div>

      {/* Add form */}
      {showAdd && (
        <div style={{ ...card, padding: '1rem', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input placeholder="id, e.g. web-01" value={newM.id}
              onChange={e => setNewM(p => ({ ...p, id: e.target.value.toLowerCase() }))} style={{ ...inputStyle, width: 150 }} />
            <select value={newM.type} onChange={e => setNewM(p => ({ ...p, type: e.target.value as 'ssh' | 'winrm' }))}
              style={{ ...inputStyle, width: 150 }}>
              <option value="ssh">Linux (SSH)</option>
              <option value="winrm">Windows (WinRM)</option>
            </select>
            <input placeholder="host / IP" value={newM.host}
              onChange={e => setNewM(p => ({ ...p, host: e.target.value }))} style={{ ...inputStyle, width: 160 }} />
            <input placeholder={newM.type === 'ssh' ? 'port (22)' : 'port (5986)'} value={newM.port}
              onChange={e => setNewM(p => ({ ...p, port: e.target.value.replace(/\D/g, '') }))} style={{ ...inputStyle, width: 100 }} />
            <input placeholder={newM.type === 'ssh' ? 'user (agentica)' : 'user (Administrator)'} value={newM.user}
              onChange={e => setNewM(p => ({ ...p, user: e.target.value }))} style={{ ...inputStyle, width: 150 }} />
            <button onClick={add} disabled={!newM.id.trim() || !newM.host.trim()} style={btnSmall('#0f2a1f', '#6ee7b7', '#166534')}>
              Save
            </button>
          </div>
          {addError && <div style={{ color: '#fca5a5', fontSize: '0.78rem', marginTop: '0.5rem' }}>{addError}</div>}
          <p style={{ color: '#444', fontSize: '0.74rem', margin: '0.6rem 0 0' }}>
            Next: set credentials, fetch &amp; trust the host key / certificate, then Test connection.
            Prepare servers with <code style={code}>infra/linux-target-setup.sh</code> or <code style={code}>infra/windows-target-setup.ps1</code>.
          </p>
        </div>
      )}

      {loaded && machines.length === 0 && !showAdd && (
        <div style={{ ...card, borderStyle: 'dashed', padding: '2rem', textAlign: 'center' }}>
          <Server size={32} color="#333" strokeWidth={1.2} style={{ marginBottom: '0.75rem' }} />
          <p style={{ color: '#666', margin: '0 0 0.4rem', fontSize: '0.9rem' }}>No remote machines registered yet.</p>
          <p style={{ color: '#444', margin: 0, fontSize: '0.8rem' }}>Click <b>Add machine</b> to register a Linux or Windows server.</p>
        </div>
      )}

      {machines.map(m => {
        const isOpen = expanded === m.id
        const st = status[m.id]
        const fp = fetched[m.id]
        const ready = m.trusted && m.has_credentials
        return (
          <div key={m.id} style={{ ...card, marginBottom: '0.75rem', overflow: 'hidden' }}>
            <div onClick={() => setExpanded(isOpen ? null : m.id)}
              style={{ padding: '0.85rem 1rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.75rem', userSelect: 'none', flexWrap: 'wrap' }}>
              <Server size={16} color={ready ? '#6ee7b7' : '#555'} strokeWidth={1.8} />
              <div style={{ flex: 1, minWidth: 180 }}>
                <span style={{ color: '#e5e5e5', fontWeight: 600, fontSize: '0.95rem' }}>{m.id}</span>
                <span style={{ color: '#555', fontSize: '0.78rem', marginLeft: 10 }}>
                  {m.type === 'ssh' ? 'Linux · SSH' : 'Windows · WinRM'} · {m.host}:{m.port} · {m.user}
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
                <Badge ok={m.trusted} on="Trusted" off="Untrusted" icon={m.trusted ? <Shield size={12} /> : <ShieldOff size={12} />} />
                <Badge ok={m.has_credentials} on="Creds set" off="No creds" icon={<KeyRound size={12} />} />
                {isOpen ? <ChevronUp size={14} color="#444" /> : <ChevronDown size={14} color="#444" />}
              </div>
            </div>

            {isOpen && (
              <div style={{ borderTop: '1px solid #1a1a1a', padding: '0.9rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                {/* 1. Credentials */}
                <Section n={1} title="Credentials (stored in the OS keyring, never on disk)">
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <input placeholder={`Username (${m.user})`} value={credForm[m.id]?.username || ''}
                      onChange={e => setCredForm(p => ({ ...p, [m.id]: { ...blankCred, ...p[m.id], username: e.target.value } }))} style={inputStyle} />
                    <input type="password" placeholder="Password" value={credForm[m.id]?.password || ''}
                      onChange={e => setCredForm(p => ({ ...p, [m.id]: { ...blankCred, ...p[m.id], password: e.target.value } }))} style={inputStyle} />
                    <button onClick={() => saveCreds(m)} style={btnSmall('#1a2a1a', '#6ee7b7', '#166534')}>
                      <KeyRound size={12} /> Save
                    </button>
                  </div>
                  {m.type === 'ssh' && (
                    <textarea placeholder="…or paste a private key (ed25519 / ECDSA / RSA, unencrypted)" rows={2}
                      value={credForm[m.id]?.private_key || ''}
                      onChange={e => setCredForm(p => ({ ...p, [m.id]: { ...blankCred, ...p[m.id], private_key: e.target.value } }))}
                      style={{ ...inputStyle, width: '100%', marginTop: '0.45rem', fontFamily: 'monospace', resize: 'vertical' }} />
                  )}
                </Section>

                {/* 2. Trust */}
                <Section n={2} title={m.type === 'ssh' ? 'Trust the SSH host key' : 'Trust the WinRM HTTPS certificate'}>
                  {m.trusted && (
                    <div style={{ fontSize: '0.75rem', color: '#6ee7b7', marginBottom: '0.45rem', overflowWrap: 'anywhere' }}>
                      Pinned: <code style={code}>{m.trusted_value}</code>
                      <button onClick={() => untrust(m)} style={{ ...btnGhost, marginLeft: 8, padding: '0.15rem 0.5rem' }}>Untrust</button>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button onClick={() => fetchFp(m)} disabled={busy === m.id + ':fp'} style={btnSmall('#141414', '#ccc', '#333')}>
                      <Fingerprint size={12} /> {busy === m.id + ':fp' ? 'Fetching…' : 'Fetch from server'}
                    </button>
                    <input placeholder={m.type === 'ssh' ? 'SHA256:… or aa:bb:… (MD5)' : 'SHA-1 thumbprint'}
                      value={trustForm[m.id] || ''} onChange={e => setTrustForm(p => ({ ...p, [m.id]: e.target.value }))}
                      style={{ ...inputStyle, flex: 1, minWidth: 220, fontFamily: 'monospace' }} />
                    <button onClick={() => trust(m)} style={btnSmall('#1e1a2a', '#c084fc', '#7c3aed')}>
                      <Shield size={12} /> Trust
                    </button>
                  </div>
                  {fp && ('error' in fp
                    ? <div style={{ color: '#fca5a5', fontSize: '0.75rem', marginTop: '0.4rem' }}>{fp.error}</div>
                    : <div style={{ color: '#888', fontSize: '0.74rem', marginTop: '0.4rem', lineHeight: 1.6, overflowWrap: 'anywhere' }}>
                        Server presented {fp.key_type ? <b>{fp.key_type}</b> : 'certificate'}:{' '}
                        <code style={code}>{fp.sha256 || fp.sha1}</code>{fp.md5 && <> · MD5 <code style={code}>{fp.md5}</code></>}
                        <br />Compare with the server ({m.type === 'ssh'
                          ? <code style={code}>ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub</code>
                          : <>thumbprint printed by <code style={code}>windows-target-setup.ps1</code></>}) before clicking Trust.
                      </div>)}
                </Section>

                {/* 3. Test */}
                <Section n={3} title="Test and use">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                    <button onClick={() => testConn(m)} disabled={busy === m.id + ':test'} style={btnSmall('#0a1a1a', '#6ee7b7', '#065f46')}>
                      <TestTube2 size={12} /> Test connection
                    </button>
                    <button onClick={() => askAgent(m)} disabled={!ready} title={ready ? '' : 'Set credentials and trust first'}
                      style={{ ...btnSmall('#0f1a2a', '#60a5fa', '#1e40af'), opacity: ready ? 1 : 0.4 }}>
                      <MessageSquare size={12} /> Ask the agent about {m.id}
                    </button>
                    <button onClick={() => remove(m.id)} style={{ ...btnSmall('#1a0f0f', '#fca5a5', '#7f1d1d'), marginLeft: 'auto' }}>
                      <Trash2 size={12} /> Remove
                    </button>
                  </div>
                </Section>

                {st && (
                  <div style={{ fontSize: '0.78rem', color: st.ok ? '#6ee7b7' : '#fca5a5', display: 'flex', alignItems: 'flex-start', gap: '6px', overflowWrap: 'anywhere' }}>
                    {st.ok ? <Wifi size={13} style={{ flexShrink: 0, marginTop: 2 }} /> : <WifiOff size={13} style={{ flexShrink: 0, marginTop: 2 }} />}
                    {st.msg}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

const blankCred = { username: '', password: '', private_key: '' }

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ color: '#555', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: '0.4rem' }}>
        {n}. {title}
      </label>
      {children}
    </div>
  )
}

function Badge({ ok, on, off, icon }: { ok: boolean; on: string; off: string; icon: React.ReactNode }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.72rem', color: ok ? '#6ee7b7' : '#fca5a5' }}>
      {icon}{ok ? on : off}
    </span>
  )
}

const card: React.CSSProperties = { background: '#111', border: '1px solid #1e1e1e', borderRadius: 10 }
const code: React.CSSProperties = { color: '#6ee7b7', background: '#1a1a1a', padding: '1px 5px', borderRadius: 4, fontSize: '0.72rem' }

const inputStyle: React.CSSProperties = {
  background: '#0a0a0a', border: '1px solid #2a2a2a', borderRadius: 6,
  padding: '0.45rem 0.65rem', color: '#e5e5e5', fontSize: '0.82rem', width: 170, boxSizing: 'border-box',
}

const btnGhost: React.CSSProperties = {
  background: '#141414', border: '1px solid #2a2a2a', color: '#888', borderRadius: 7,
  padding: '0.4rem 0.75rem', cursor: 'pointer', fontSize: '0.8rem',
}

function btnSmall(bg: string, color: string, border: string): React.CSSProperties {
  return {
    background: bg, color, border: `1px solid ${border}`, borderRadius: 6,
    padding: '0.45rem 0.75rem', cursor: 'pointer', fontSize: '0.78rem', fontWeight: 600,
    display: 'flex', alignItems: 'center', gap: '0.3rem', whiteSpace: 'nowrap',
  }
}
