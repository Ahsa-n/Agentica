import React, { useEffect, useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, MessageSquare, BookOpen, Server, Activity } from 'lucide-react'
import ChatPage from './pages/ChatPage'
import KnowledgePage from './pages/KnowledgePage'
import MachinesPage from './pages/MachinesPage'
import DashboardPage from './pages/DashboardPage'

const NAV = [
  { to: '/',          label: 'Dashboard',     Icon: LayoutDashboard },
  { to: '/chat',      label: 'Chat',           Icon: MessageSquare   },
  { to: '/knowledge', label: 'Knowledge Base', Icon: BookOpen        },
  { to: '/machines',  label: 'Machines',       Icon: Server          },
]

export default function App() {
  const [healthy, setHealthy] = useState<boolean | null>(null)

  useEffect(() => {
    const check = () =>
      fetch('/api/health').then(r => setHealthy(r.ok)).catch(() => setHealthy(false))
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <nav className="app-sidebar" style={{ background: '#111', borderRight: '1px solid #1e1e1e', display: 'flex', flexDirection: 'column' }}>
        {/* Brand */}
        <div style={{ padding: '1rem 0.9rem 0.9rem', borderBottom: '1px solid #1e1e1e', display: 'flex', alignItems: 'center', gap: '0.5rem', overflow: 'hidden' }}>
          <Activity size={18} color="#6ee7b7" strokeWidth={2.5} style={{ flexShrink: 0 }} />
          <div className="sidebar-brand-text" style={{ overflow: 'hidden' }}>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff', letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>Agentica</div>
            <div style={{ fontSize: '0.65rem', color: '#444', whiteSpace: 'nowrap' }}>IT Operations Agent</div>
          </div>
        </div>

        {/* Nav */}
        <div style={{ flex: 1, padding: '0.5rem 0' }}>
          {NAV.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} end={to === '/'}
              className="nav-item"
              title={label}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: '0.65rem',
                padding: '0.6rem 0.9rem',
                color: isActive ? '#6ee7b7' : '#666',
                textDecoration: 'none',
                background: isActive ? 'rgba(110,231,183,0.07)' : 'transparent',
                borderLeft: `2px solid ${isActive ? '#6ee7b7' : 'transparent'}`,
                fontSize: '0.875rem',
                fontWeight: isActive ? 500 : 400,
                transition: 'all 0.12s',
                overflow: 'hidden',
                whiteSpace: 'nowrap',
              })}>
              <Icon size={16} strokeWidth={1.8} style={{ flexShrink: 0 }} />
              <span className="sidebar-label">{label}</span>
            </NavLink>
          ))}
        </div>

        {/* Status */}
        <div style={{ padding: '0.65rem 0.9rem', borderTop: '1px solid #1e1e1e', display: 'flex', alignItems: 'center', gap: '0.5rem', overflow: 'hidden' }}>
          <span style={{
            width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
            background: healthy === null ? '#555' : healthy ? '#6ee7b7' : '#fca5a5',
            boxShadow: healthy ? '0 0 5px rgba(110,231,183,0.5)' : 'none',
          }} />
          <span className="sidebar-status-text" style={{ fontSize: '0.7rem', color: '#444', whiteSpace: 'nowrap' }}>
            {healthy === null ? 'Connecting…' : healthy ? 'Backend online' : 'Backend offline'}
          </span>
        </div>
      </nav>

      {/* Main */}
      <main className="app-main">
        <Routes>
          <Route path="/"                element={<DashboardPage />} />
          <Route path="/chat"            element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/knowledge"       element={<KnowledgePage />} />
          <Route path="/machines"        element={<MachinesPage />} />
        </Routes>
      </main>
    </div>
  )
}
