import React from 'react'
import { useNavigate } from 'react-router-dom'
import { apiPost } from '../api/client'

interface TaskCard {
  id: string
  title: string
  description: string
  categories: string[]
  examples: string[]
  disabled?: boolean
  comingSoon?: string
}

const CARDS: TaskCard[] = [
  {
    id: 'monitoring',
    title: 'System Monitoring',
    description: 'CPU, memory, disk, network, and process monitoring',
    categories: ['monitoring'],
    examples: ['What is the CPU usage?', 'Show me disk usage', 'List top processes'],
  },
  {
    id: 'services',
    title: 'Services & Applications',
    description: 'Service status, start/stop/restart, application health',
    categories: ['services', 'applications'],
    examples: ['Is nginx running?', 'Restart postgresql', 'Show application status'],
  },
  {
    id: 'remote',
    title: 'Remote Servers',
    description: 'Monitor and manage remote Linux and Windows servers',
    categories: ['remote'],
    examples: ['Check CPU on linux-server-1', 'Restart nginx on remote server'],
  },
  {
    id: 'knowledge',
    title: 'Knowledge Base',
    description: 'Search SOPs, runbooks, and procedures',
    categories: ['knowledge'],
    examples: ['How to handle a full disk?', 'Nginx restart procedure'],
  },
  {
    id: 'files',
    title: 'File Operations',
    description: 'File management and operations',
    categories: [],
    examples: [],
    disabled: true,
    comingSoon: 'FYP-II',
  },
  {
    id: 'troubleshooting',
    title: 'Guided Troubleshooting',
    description: 'Step-by-step troubleshooting workflows',
    categories: [],
    examples: [],
    disabled: true,
    comingSoon: 'FYP-II',
  },
]

export default function DashboardPage() {
  const navigate = useNavigate()

  const handleCardClick = async (card: TaskCard) => {
    if (card.disabled) return
    const { id } = await apiPost<{ id: string }>('/api/sessions')
    navigate(`/chat/${id}`, { state: { forceCategories: card.categories, examples: card.examples } })
  }

  return (
    <div style={{ padding: '2rem', maxWidth: 900, margin: '0 auto' }}>
      <h2 style={{ margin: '0 0 0.5rem', color: '#e5e5e5' }}>What would you like to do?</h2>
      <p style={{ margin: '0 0 2rem', color: '#888', fontSize: '0.9rem' }}>
        Select a task area or go to Chat to ask anything.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '1rem' }}>
        {CARDS.map(card => (
          <div
            key={card.id}
            onClick={() => handleCardClick(card)}
            style={{
              background: '#1a1a1a',
              border: `1px solid ${card.disabled ? '#2a2a2a' : '#3a3a3a'}`,
              borderRadius: 8,
              padding: '1.25rem',
              cursor: card.disabled ? 'not-allowed' : 'pointer',
              opacity: card.disabled ? 0.5 : 1,
              transition: 'border-color 0.15s, background 0.15s',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <h3 style={{ margin: '0 0 0.5rem', fontSize: '1rem', color: card.disabled ? '#666' : '#e5e5e5' }}>
                {card.title}
              </h3>
              {card.comingSoon && (
                <span style={{ fontSize: '0.65rem', background: '#2a2a2a', color: '#888', padding: '2px 6px', borderRadius: 4 }}>
                  {card.comingSoon}
                </span>
              )}
            </div>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.8rem', color: '#888' }}>{card.description}</p>
            {!card.disabled && card.examples.length > 0 && (
              <ul style={{ margin: 0, padding: '0 0 0 1rem', fontSize: '0.75rem', color: '#6ee7b7' }}>
                {card.examples.slice(0, 2).map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
