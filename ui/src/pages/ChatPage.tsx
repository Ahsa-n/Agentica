import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import DOMPurify from 'dompurify'
import { apiDelete, apiGet, apiPost } from '../api/client'
import { streamMessage, SSEEvent } from '../api/sse'
import ToolCallCard from '../components/ToolCallCard'
import ApprovalPrompt from '../components/ApprovalPrompt'

interface SessionInfo { id: string; title: string | null; updated_at: string }
interface ToolCallState {
  call_id: string; tool: string; args: Record<string, unknown>
  decision?: string; reason?: string; rule_id?: string
  result?: unknown; duration_ms?: number
  awaitingApproval?: boolean
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCallState[]
  streaming?: boolean
}

const EXAMPLES = [
  'What is the CPU usage right now?',
  'Show me disk usage on all drives',
  'Is nginx running?',
  'How do I handle a full disk? (search KB)',
]

export default function ChatPage() {
  const { sessionId: paramId } = useParams<{ sessionId?: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const { forceCategories = [], examples = EXAMPLES } = (location.state as any) || {}

  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [currentId, setCurrentId] = useState<string | null>(paramId || null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadSessions = async () => {
    const data = await apiGet<SessionInfo[]>('/api/sessions')
    setSessions(data)
  }

  useEffect(() => { loadSessions() }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const newSession = async () => {
    const { id } = await apiPost<{ id: string }>('/api/sessions')
    setCurrentId(id)
    setMessages([])
    navigate(`/chat/${id}`, { state: location.state })
    await loadSessions()
  }

  const deleteSession = async (id: string) => {
    await apiDelete(`/api/sessions/${id}`)
    if (id === currentId) { setCurrentId(null); setMessages([]) }
    await loadSessions()
  }

  const send = async () => {
    const content = input.trim()
    if (!content || running) return
    if (!currentId) { await newSession(); return }

    setInput('')
    setRunning(true)

    const userMsg: Message = { role: 'user', content }
    const assistantMsg: Message = { role: 'assistant', content: '', streaming: true, toolCalls: [] }
    setMessages(prev => [...prev, userMsg, assistantMsg])

    abortRef.current = new AbortController()

    try {
      await streamMessage({
        sessionId: currentId,
        content,
        forceCategories,
        signal: abortRef.current.signal,
        onEvent: (evt: SSEEvent) => {
          setMessages(prev => {
            const msgs = [...prev]
            const last = msgs[msgs.length - 1]
            if (!last || last.role !== 'assistant') return msgs

            if (evt.type === 'policy_decision') {
              const tc: ToolCallState = {
                call_id: evt.data.call_id,
                tool: evt.data.tool,
                args: {},
                decision: evt.data.decision,
                reason: evt.data.reason,
                rule_id: evt.data.rule_id,
              }
              last.toolCalls = [...(last.toolCalls || []), tc]
            } else if (evt.type === 'approval_required') {
              last.toolCalls = (last.toolCalls || []).map(tc =>
                tc.call_id === evt.data.call_id
                  ? { ...tc, awaitingApproval: true, args: evt.data.args }
                  : tc
              )
              if (!last.toolCalls.find(tc => tc.call_id === evt.data.call_id)) {
                last.toolCalls = [...last.toolCalls, { ...evt.data, awaitingApproval: true }]
              }
            } else if (evt.type === 'tool_end') {
              last.toolCalls = (last.toolCalls || []).map(tc =>
                tc.call_id === evt.data.call_id
                  ? { ...tc, result: evt.data.result, duration_ms: evt.data.duration_ms, awaitingApproval: false }
                  : tc
              )
            } else if (evt.type === 'token') {
              last.content += evt.data.text
            } else if (evt.type === 'final') {
              last.content = evt.data.answer
              last.streaming = false
            } else if (evt.type === 'error') {
              last.content = `Error: ${evt.data.message}`
              last.streaming = false
            }

            return msgs
          })
        },
        onDone: () => {
          setRunning(false)
          setMessages(prev => {
            const msgs = [...prev]
            const last = msgs[msgs.length - 1]
            if (last) last.streaming = false
            return msgs
          })
          loadSessions()
        },
      })
    } catch {
      setRunning(false)
    }
  }

  const cancel = async () => {
    abortRef.current?.abort()
    if (currentId) await apiPost(`/api/sessions/${currentId}/cancel`)
    setRunning(false)
  }

  const approve = async (callId: string, sessionId: string, approved: boolean) => {
    await apiPost(`/api/sessions/${sessionId}/approvals/${callId}`, { approved })
  }

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Session sidebar */}
      <div style={{ width: 220, borderRight: '1px solid #2a2a2a', background: '#161616', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '0.75rem' }}>
          <button onClick={newSession} style={btnStyle('#6ee7b7', '#0f0f0f', '100%')}>
            + New Session
          </button>
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {sessions.map(s => (
            <div key={s.id}
              onClick={() => { setCurrentId(s.id); navigate(`/chat/${s.id}`) }}
              style={{
                padding: '0.6rem 0.75rem',
                cursor: 'pointer',
                background: s.id === currentId ? 'rgba(110,231,183,0.08)' : 'transparent',
                borderLeft: s.id === currentId ? '3px solid #6ee7b7' : '3px solid transparent',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                fontSize: '0.8rem', color: '#ccc',
              }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.title || 'Session'}
              </span>
              <button
                onClick={e => { e.stopPropagation(); deleteSession(s.id) }}
                style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', padding: '0 2px', fontSize: '0.9rem' }}>
                ×
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Messages */}
        <div style={{ flex: 1, overflow: 'auto', padding: '1.5rem' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: '4rem', color: '#555' }}>
              <p style={{ fontSize: '1.1rem', marginBottom: '1.5rem' }}>How can I help?</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', justifyContent: 'center' }}>
                {examples.slice(0, 4).map((e: string, i: number) => (
                  <button key={i} onClick={() => { setInput(e) }}
                    style={{ background: '#1a1a1a', border: '1px solid #333', color: '#aaa', padding: '0.4rem 0.8rem', borderRadius: 20, cursor: 'pointer', fontSize: '0.8rem' }}>
                    {e}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ marginBottom: '1.5rem' }}>
              {msg.role === 'user' ? (
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <div style={{ background: '#2a2a2a', borderRadius: '12px 12px 2px 12px', padding: '0.75rem 1rem', maxWidth: '75%', fontSize: '0.9rem' }}>
                    {msg.content}
                  </div>
                </div>
              ) : (
                <div>
                  {/* Tool calls */}
                  {msg.toolCalls?.map(tc => (
                    <div key={tc.call_id}>
                      <ToolCallCard toolCall={tc} />
                      {tc.awaitingApproval && currentId && (
                        <ApprovalPrompt
                          toolCall={tc}
                          onApprove={() => approve(tc.call_id, currentId, true)}
                          onDeny={() => approve(tc.call_id, currentId, false)}
                        />
                      )}
                    </div>
                  ))}
                  {/* Answer */}
                  {msg.content && (
                    <div style={{ background: '#1a1a1a', borderRadius: '2px 12px 12px 12px', padding: '0.75rem 1rem', maxWidth: '90%', fontSize: '0.9rem', lineHeight: 1.6 }}>
                      <ReactMarkdown>{DOMPurify.sanitize(msg.content)}</ReactMarkdown>
                      {msg.streaming && <span style={{ color: '#6ee7b7' }}>▌</span>}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        <div style={{ padding: '1rem', borderTop: '1px solid #2a2a2a', display: 'flex', gap: '0.5rem' }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
            placeholder={currentId ? 'Ask about your systems...' : 'Create a session to start chatting'}
            disabled={!currentId || running}
            style={{
              flex: 1, background: '#1a1a1a', border: '1px solid #333', borderRadius: 8,
              padding: '0.75rem 1rem', color: '#e5e5e5', fontSize: '0.9rem', outline: 'none',
            }}
          />
          {running ? (
            <button onClick={cancel} style={btnStyle('#ef4444', '#fff')}>Stop</button>
          ) : (
            <button onClick={send} disabled={!currentId || !input.trim()} style={btnStyle('#6ee7b7', '#0f0f0f')}>
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function btnStyle(bg: string, color: string, width?: string): React.CSSProperties {
  return {
    background: bg, color, border: 'none', borderRadius: 8,
    padding: '0.6rem 1.2rem', cursor: 'pointer', fontWeight: 600,
    fontSize: '0.85rem', width,
  }
}
