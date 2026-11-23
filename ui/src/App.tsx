import React, { useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import KnowledgePage from './pages/KnowledgePage'
import MachinesPage from './pages/MachinesPage'
import DashboardPage from './pages/DashboardPage'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/chat', label: 'Chat' },
  { to: '/knowledge', label: 'Knowledge Base' },
  { to: '/machines', label: 'Machines' },
]

export default function App() {
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <nav style={{
        width: 220, background: '#1a1a1a', borderRight: '1px solid #2a2a2a',
        display: 'flex', flexDirection: 'column', padding: '1rem 0'
      }}>
        <div style={{ padding: '0 1rem 1.5rem', borderBottom: '1px solid #2a2a2a', marginBottom: '1rem' }}>
          <h1 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 700, color: '#6ee7b7' }}>Agentica</h1>
          <p style={{ margin: 0, fontSize: '0.7rem', color: '#666' }}>IT Operations Agent</p>
        </div>
        {NAV.map(n => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'}
            style={({ isActive }) => ({
              padding: '0.6rem 1rem',
              color: isActive ? '#6ee7b7' : '#aaa',
              textDecoration: 'none',
              background: isActive ? 'rgba(110,231,183,0.08)' : 'transparent',
              borderLeft: isActive ? '3px solid #6ee7b7' : '3px solid transparent',
              fontSize: '0.9rem',
              transition: 'all 0.15s',
            })}
          >{n.label}</NavLink>
        ))}
      </nav>

      {/* Main content */}
      <main style={{ flex: 1, overflow: 'auto' }}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/machines" element={<MachinesPage />} />
        </Routes>
      </main>
    </div>
  )
}
