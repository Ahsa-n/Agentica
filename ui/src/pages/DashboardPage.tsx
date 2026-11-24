import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Cpu, Network, Server, BookOpen,
  MessageSquare, ChevronRight, Clock,
} from 'lucide-react'
import { apiGet, apiPost } from '../api/client'

interface TaskCard {
  id: string; title: string; description: string
  icon: React.ReactNode; categories: string[]; examples: string[]
  disabled?: boolean; comingSoon?: string
}

const CARDS: TaskCard[] = [
  {
    id: 'monitoring', title: 'System Monitoring',
    icon: <Cpu size={20} strokeWidth={1.8} color="#6ee7b7" />,
    description: 'CPU, memory, disk, network, top processes',
    categories: ['monitoring'],
    examples: ['What is the CPU usage right now?', 'Show me disk usage on all drives', 'List top 5 processes by memory'],
  },
  {
    id: 'services', title: 'Services & Applications',
    icon: <Server size={20} strokeWidth={1.8} color="#60a5fa" />,
    description: 'Start, stop, restart services and check health',
    categories: ['services', 'applications'],
    examples: ['Is nginx running?', 'Restart postgresql', 'Show all stopped services'],
  },
  {
    id: 'remote', title: 'Remote Servers',
    icon: <Network size={20} strokeWidth={1.8} color="#c084fc" />,
    description: 'Monitor and manage remote Linux and Windows servers via SSH/WinRM',
    categories: ['remote'],
    examples: ['Check CPU on linux-server-1', 'Restart nginx on remote server'],
  },
  {
    id: 'knowledge', title: 'Knowledge Base',
    icon: <BookOpen size={20} strokeWidth={1.8} color="#fbbf24" />,
    description: 'Search SOPs, runbooks, and incident procedures',
    categories: ['knowledge'],
    examples: ['How to handle a full disk?', 'Nginx restart SOP', 'Memory alert threshold'],
  },
]

interface StatItem { label: string; value: string | number; color?: string }

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<StatItem[]>([])
  const [recentSessions, setRecentSessions] = useState<any[]>([])
  const [hover, setHover] = useState<string | null>(null)

  const [firstMachine, setFirstMachine] = useState<string | null>(null)

  useEffect(() => {
    apiGet<{ id: string }[]>('/api/machines').then(m => setFirstMachine(m[0]?.id ?? null)).catch(() => {})
    Promise.all([
      apiGet<any[]>('/api/sessions'),
      apiGet<any[]>('/api/knowledge/documents'),
    ]).then(([sessions, docs]) => {
      setRecentSessions(sessions.slice(0, 5))
      const okDocs = docs.filter((d: any) => d.status === 'ok')
      const totalChunks = okDocs.reduce((sum: number, d: any) => sum + (d.chunk_count || 0), 0)
      setStats([
        { label: 'Sessions', value: sessions.length, color: '#6ee7b7' },
        { label: 'KB Documents', value: okDocs.length, color: '#fbbf24' },
        { label: 'KB Chunks', value: totalChunks, color: '#60a5fa' },
        { label: 'Model', value: 'qwen2.5:7b', color: '#c084fc' },
      ])
    }).catch(() => {})
  }, [])

  // Remote examples name a real registered machine when there is one.
  const examplesFor = (card: TaskCard) => card.id !== 'remote' ? card.examples
    : firstMachine
      ? [`Check CPU and memory on ${firstMachine}`, `Is nginx running on ${firstMachine}?`,
         `Show disk usage on ${firstMachine}`, `Restart nginx on ${firstMachine}`]
      : ['Register a server on the Machines page first, then ask e.g. "Check CPU on web-01"']

  const handleCardClick = async (card: TaskCard) => {
    if (card.disabled) return
    const { id } = await apiPost<{ id: string }>('/api/sessions')
    navigate(`/chat/${id}`, { state: { forceCategories: card.categories, examples: examplesFor(card) } })
  }

  return (
    <div className="page-pad" style={{ maxWidth: 960, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '1.75rem' }}>
        <h2 style={{ margin: '0 0 0.3rem', color: '#fff', fontSize: '1.3rem', fontWeight: 600 }}>
          What would you like to do?
        </h2>
        <p style={{ margin: 0, color: '#666', fontSize: '0.875rem' }}>
          Select a task area or go to Chat to ask anything in natural language.
        </p>
      </div>

      {/* Stats strip */}
      {stats.length > 0 && (
        <div className="stats-strip" style={{ marginBottom: '1.75rem' }}>
          {stats.map(s => (
            <div key={s.label} style={{
              background: '#141414', border: '1px solid #222', borderRadius: 8,
              padding: '0.75rem 1.25rem', minWidth: 110,
            }}>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: s.color || '#e5e5e5', lineHeight: 1 }}>
                {s.value}
              </div>
              <div style={{ fontSize: '0.72rem', color: '#555', marginTop: '0.3rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {s.label}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Task cards */}
      <div className="dash-grid" style={{ marginBottom: '2rem' }}>
        {CARDS.map(card => (
          <div
            key={card.id}
            className={card.disabled ? '' : 'card-hover-green'}
            onClick={() => handleCardClick(card)}
            style={{
              background: '#141414',
              border: `1px solid ${hover === card.id && !card.disabled ? '#6ee7b7' : '#222'}`,
              borderRadius: 10, padding: '1.25rem',
              cursor: card.disabled ? 'not-allowed' : 'pointer',
              opacity: card.disabled ? 0.45 : 1,
              transition: 'border-color 0.15s, background 0.15s',
            }}
            onMouseEnter={() => setHover(card.id)}
            onMouseLeave={() => setHover(null)}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.6rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                {card.icon}
                <span style={{ color: card.disabled ? '#555' : '#e5e5e5', fontWeight: 600, fontSize: '0.95rem' }}>
                  {card.title}
                </span>
              </div>
              {card.comingSoon && (
                <span className="tag" style={{ background: '#1a1a1a', color: '#555', border: '1px solid #2a2a2a' }}>
                  {card.comingSoon}
                </span>
              )}
            </div>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.8rem', color: '#666', lineHeight: 1.5 }}>
              {card.description}
            </p>
            {!card.disabled && card.examples.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                {examplesFor(card).slice(0, 2).map((e, i) => (
                  <div key={i} style={{ fontSize: '0.74rem', color: '#6ee7b7', opacity: 0.75 }}>
                    › {e}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Recent sessions */}
      {recentSessions.length > 0 && (
        <div>
          <h3 style={{ color: '#888', fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 0.75rem' }}>
            Recent Sessions
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {recentSessions.map(s => (
              <div
                key={s.id}
                className="card-hover"
                onClick={() => navigate(`/chat/${s.id}`)}
                style={{
                  background: '#141414', border: '1px solid #1e1e1e', borderRadius: 7,
                  padding: '0.6rem 1rem', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: '0.75rem',
                }}>
                <MessageSquare size={14} color="#555" strokeWidth={1.8} />
                <span style={{ flex: 1, fontSize: '0.85rem', color: '#ccc' }}>
                  {s.title || 'Untitled session'}
                </span>
                <Clock size={12} color="#444" strokeWidth={1.8} />
                <span style={{ fontSize: '0.72rem', color: '#444' }}>
                  {new Date(s.updated_at).toLocaleDateString()}
                </span>
                <ChevronRight size={14} color="#444" strokeWidth={1.8} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
