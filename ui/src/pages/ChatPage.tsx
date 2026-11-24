import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import DOMPurify from 'dompurify'
import { Plus, Trash2, Send, StopCircle, Tag } from 'lucide-react'
import { apiDelete, apiGet, apiPost } from '../api/client'
import { streamMessage, SSEEvent } from '../api/sse'
import ToolCallCard, { ToolCallState } from '../components/ToolCallCard'
import ApprovalPrompt from '../components/ApprovalPrompt'

interface SessionInfo { id: string; title: string | null; updated_at: string }

interface HistoryMessage { role: 'user' | 'assistant'; content: string; toolCalls?: ToolCallState[] }

interface ApprovalResponse {
  ok: boolean; approved: boolean; answer?: string; error?: string
  tool_call?: ToolCallState | null
  next_approval?: ToolCallState | null
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCallState[]
  streaming?: boolean
  categories?: string[]
  thinking?: boolean
}

const CATEGORY_COLORS: Record<string, string> = {
  monitoring:   '#6ee7b7',
  services:     '#60a5fa',
  applications: '#60a5fa',
  knowledge:    '#fbbf24',
  remote:       '#c084fc',
  logs:         '#f97316',
  network:      '#34d399',
}

const DEFAULT_EXAMPLES = [
  'What is the current CPU and memory usage?',
  'Is nginx running? Check its status.',
  'How do I handle a full disk? (search KB)',
  'List the top 5 processes by memory usage',
]

function Thinking({ working }: { working: boolean }) {
  const [secs, setSecs] = useState(0)
  useEffect(() => {
    const t0 = Date.now()
    const id = setInterval(() => setSecs(Math.floor((Date.now() - t0) / 1000)), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: '0.25rem 0 0.5rem', padding: '0.5rem 0', flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
        <span className="dot1" /><span className="dot2" /><span className="dot3" />
      </div>
      <span style={{ color: '#666', fontSize: '0.78rem' }}>
        {working ? 'Agent is working with the tool results…' : 'Agent is thinking…'} {secs}s
      </span>
      {secs >= 20 && (
        <span style={{ color: '#444', fontSize: '0.72rem', width: '100%' }}>
          The local model runs on this computer's CPU, so replies can take a minute or more.
        </span>
      )}
    </div>
  )
}

export default function ChatPage() {
  const { sessionId: paramId } = useParams<{ sessionId?: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const { forceCategories = [], examples = DEFAULT_EXAMPLES } = (location.state as any) || {}

  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [currentId, setCurrentId] = useState<string | null>(paramId || null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  // Session we just created ourselves: its history is empty, and loading it would
  // wipe the message that is already streaming.
  const createdRef = useRef<string | null>(null)

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await apiGet<SessionInfo[]>('/api/sessions'))
    } catch {
      /* backend offline — sidebar status dot already shows it */
    }
  }, [])

  const loadHistory = useCallback(async (id: string) => {
    setMessages([])
    try {
      const hist = await apiGet<HistoryMessage[]>(`/api/sessions/${id}/messages`)
      setMessages(hist.map(h => ({ role: h.role, content: h.content, toolCalls: h.toolCalls || [], streaming: false })))
    } catch (e: any) {
      setMessages([{ role: 'assistant', content: `**Error loading history:** ${e?.message || e}` }])
    }
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])

  // Open the session in the URL (sidebar click, dashboard "recent sessions", reload).
  useEffect(() => {
    if (!paramId || paramId === createdRef.current) return
    setCurrentId(paramId)
    loadHistory(paramId)
  }, [paramId, loadHistory])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const newSession = async (): Promise<string> => {
    const { id } = await apiPost<{ id: string }>('/api/sessions')
    createdRef.current = id
    setCurrentId(id)
    setMessages([])
    navigate(`/chat/${id}`, { state: location.state })
    await loadSessions()
    return id
  }

  const deleteSession = async (id: string) => {
    await apiDelete(`/api/sessions/${id}`)
    if (id === currentId) {
      setCurrentId(null)
      setMessages([])
      navigate('/chat')
    }
    await loadSessions()
  }

  const sendingRef = useRef(false)

  const send = async () => {
    const content = input.trim()
    if (!content || running || sendingRef.current) return

    // Lock immediately: creating the session is async, and a second click in that
    // window used to create a second session and send the message twice.
    sendingRef.current = true
    setInput('')
    setRunning(true)

    let activeSessionId = currentId
    if (!activeSessionId) {
      try {
        activeSessionId = await newSession()
      } catch (e: any) {
        sendingRef.current = false
        setRunning(false)
        setInput(content)
        setMessages(prev => [...prev, { role: 'assistant', content: `**Error:** could not create a session (${e?.message || e})` }])
        return
      }
    }
    sendingRef.current = false

    const userMsg: Message = { role: 'user', content }
    const assistantMsg: Message = { role: 'assistant', content: '', streaming: true, toolCalls: [], thinking: true }
    setMessages(prev => [...prev, userMsg, assistantMsg])

    abortRef.current = new AbortController()

    try {
      await streamMessage({
        sessionId: activeSessionId,
        content,
        forceCategories,
        signal: abortRef.current.signal,
        onEvent: (evt: SSEEvent) => {
          setMessages(prev => {
            const msgs = [...prev]
            const last = msgs[msgs.length - 1]
            if (!last || last.role !== 'assistant') return msgs
            const updated = { ...last }

            if (evt.type === 'route') {
              updated.categories = evt.data.categories
              updated.thinking = false
            } else if (evt.type === 'policy_decision') {
              const existing = (updated.toolCalls || []).find(tc => tc.call_id === evt.data.call_id)
              if (!existing) {
                updated.toolCalls = [...(updated.toolCalls || []), {
                  call_id: evt.data.call_id, tool: evt.data.tool, args: evt.data.args || {},
                  target_id: evt.data.target_id,
                  decision: evt.data.decision, reason: evt.data.reason, rule_id: evt.data.rule_id,
                }]
              } else {
                updated.toolCalls = (updated.toolCalls || []).map(tc =>
                  tc.call_id === evt.data.call_id
                    ? { ...tc, decision: evt.data.decision, reason: evt.data.reason, rule_id: evt.data.rule_id }
                    : tc
                )
              }
              updated.thinking = false
            } else if (evt.type === 'approval_required') {
              updated.toolCalls = (updated.toolCalls || []).map(tc =>
                tc.call_id === evt.data.call_id
                  ? { ...tc, awaitingApproval: true, args: evt.data.args }
                  : tc
              )
              if (!(updated.toolCalls || []).find(tc => tc.call_id === evt.data.call_id)) {
                updated.toolCalls = [...(updated.toolCalls || []), { ...evt.data, awaitingApproval: true }]
              }
              updated.thinking = false
            } else if (evt.type === 'tool_end') {
              if (!(updated.toolCalls || []).find(tc => tc.call_id === evt.data.call_id)) {
                updated.toolCalls = [...(updated.toolCalls || []), {
                  call_id: evt.data.call_id, tool: evt.data.tool, args: evt.data.args || {},
                  target_id: evt.data.target_id,
                }]
              }
              updated.toolCalls = (updated.toolCalls || []).map(tc =>
                tc.call_id === evt.data.call_id
                  ? { ...tc, result: evt.data.result, duration_ms: evt.data.duration_ms, awaitingApproval: false }
                  : tc
              )
              updated.thinking = false
            } else if (evt.type === 'token') {
              updated.content = (updated.content || '') + evt.data.text
              updated.thinking = false
            } else if (evt.type === 'final') {
              updated.content = evt.data.answer
              updated.streaming = false
              updated.thinking = false
            } else if (evt.type === 'error') {
              updated.content = `**Error:** ${evt.data.message}`
              updated.streaming = false
              updated.thinking = false
            }

            msgs[msgs.length - 1] = updated
            return msgs
          })
        },
        onDone: () => {
          setRunning(false)
          setMessages(prev => {
            const msgs = [...prev]
            const last = msgs[msgs.length - 1]
            if (last) { msgs[msgs.length - 1] = { ...last, streaming: false, thinking: false } }
            return msgs
          })
          loadSessions()
        },
      })
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        setMessages(prev => {
          const msgs = [...prev]
          const last = msgs[msgs.length - 1]
          if (last?.role === 'assistant') {
            msgs[msgs.length - 1] = { ...last, content: `**Error:** ${e?.message || 'Unknown error'}`, streaming: false, thinking: false }
          }
          return msgs
        })
      }
      setRunning(false)
    }
  }

  const cancel = async () => {
    abortRef.current?.abort()
    if (currentId) await apiPost(`/api/sessions/${currentId}/cancel`)
    setRunning(false)
  }

  const approve = async (callId: string, sessionId: string, approved: boolean) => {
    setRunning(true)
    try {
      const result = await apiPost<ApprovalResponse>(
        `/api/sessions/${sessionId}/approvals/${callId}`,
        { approved }
      )
      setMessages(prev => {
        // Mark the card as decided and attach the tool's real result.
        const msgs = prev.map(m => !m.toolCalls ? m : {
          ...m,
          toolCalls: m.toolCalls.map(tc => tc.call_id !== callId ? tc : {
            ...tc,
            ...(result.tool_call ? { result: result.tool_call.result, duration_ms: result.tool_call.duration_ms ?? undefined } : {}),
            awaitingApproval: false,
            approval: approved ? 'approved' as const : 'denied' as const,
          }),
        })
        const text = result.ok ? result.answer : `**Error:** ${result.error || 'approval failed'}`
        if (text || result.next_approval) {
          msgs.push({
            role: 'assistant', content: text || '', streaming: false,
            toolCalls: result.next_approval ? [result.next_approval] : [],
          })
        }
        return msgs
      })
    } finally {
      setRunning(false)
      loadSessions()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="chat-shell">
      {/* Session sidebar */}
      <div className="chat-sessions" style={{ borderRight: '1px solid #1e1e1e', background: '#0d0d0d', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '0.65rem' }}>
          <button onClick={() => newSession()} className="btn-new-session">
            <Plus size={14} strokeWidth={2.5} /> New Session
          </button>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '0 0.4rem' }}>
          {sessions.map(s => (
            <div
              key={s.id}
              className="session-item"
              onClick={() => { if (!running && s.id !== currentId) navigate(`/chat/${s.id}`) }}
              style={{
                padding: '0.55rem 0.6rem',
                cursor: 'pointer',
                background: s.id === currentId ? 'rgba(110,231,183,0.07)' : 'transparent',
                borderLeft: `2px solid ${s.id === currentId ? '#6ee7b7' : 'transparent'}`,
                borderRadius: '0 6px 6px 0',
                display: 'flex', alignItems: 'center', gap: '0.5rem',
                fontSize: '0.8rem', color: s.id === currentId ? '#ccc' : '#666',
                marginBottom: 2,
              }}>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.title || 'Session'}
              </span>
              <button
                onClick={e => { e.stopPropagation(); deleteSession(s.id) }}
                className="icon-btn"
                style={{
                  background: 'none', border: 'none', color: '#3a3a3a', cursor: 'pointer',
                  padding: '2px 3px', borderRadius: 4, display: 'flex', alignItems: 'center', flexShrink: 0,
                }}>
                <Trash2 size={11} strokeWidth={1.8} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="chat-area">
        {/* Messages */}
        <div className="chat-messages">
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: '5rem', color: '#444' }}>
              <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>⚡</div>
              <p style={{ fontSize: '1rem', color: '#666', marginBottom: '1.5rem' }}>
                {currentId ? 'Ask about your systems…' : 'Start a new session to chat'}
              </p>
              {(examples as string[]).slice(0, 4).map((e: string, i: number) => (
                <button
                  key={i}
                  className="example-btn"
                  onClick={() => setInput(e)}
                  style={{
                    display: 'block', margin: '0 auto 0.4rem',
                    background: '#141414', border: '1px solid #222', color: '#888',
                    padding: '0.45rem 1rem', borderRadius: 20, cursor: 'pointer',
                    fontSize: '0.82rem', transition: 'all 0.12s', maxWidth: 420, width: '100%',
                  }}>
                  {e}
                </button>
              ))}
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className="msg-enter" style={{ marginBottom: '1.5rem' }}>
              {msg.role === 'user' ? (
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <div style={{
                    background: '#1e1e1e', borderRadius: '14px 14px 2px 14px',
                    padding: '0.7rem 1rem', maxWidth: '78%',
                    fontSize: '0.9rem', lineHeight: 1.6, color: '#e5e5e5',
                    border: '1px solid #2a2a2a',
                  }}>
                    {msg.content}
                  </div>
                </div>
              ) : (
                <div style={{ maxWidth: '88%' }}>
                  {/* Route categories */}
                  {msg.categories && msg.categories.length > 0 && (
                    <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
                      <Tag size={12} color="#3a3a3a" strokeWidth={1.8} style={{ marginTop: 2 }} />
                      {msg.categories.map(cat => (
                        <span key={cat} className="tag" style={{
                          background: 'transparent',
                          color: CATEGORY_COLORS[cat] || '#888',
                          border: `1px solid ${CATEGORY_COLORS[cat] || '#333'}33`,
                          opacity: 0.8,
                        }}>
                          {cat}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Thinking indicator — shown until the answer arrives, with elapsed time */}
                  {msg.streaming && !msg.content && <Thinking working={(msg.toolCalls || []).length > 0} />}

                  {/* Tool calls */}
                  {(msg.toolCalls || []).map(tc => (
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
                    <div style={{
                      background: '#111', borderRadius: '2px 14px 14px 14px',
                      padding: '0.75rem 1rem', fontSize: '0.9rem', lineHeight: 1.7,
                      border: '1px solid #1e1e1e',
                    }}>
                      <ReactMarkdown>{DOMPurify.sanitize(msg.content)}</ReactMarkdown>
                      {msg.streaming && <span className="cursor-blink">▌</span>}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="chat-input-bar">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={currentId ? 'Ask about your systems… (Enter to send, Shift+Enter for newline)' : 'Type a message to start…'}
            disabled={running}
            rows={1}
            className="chat-textarea"
            onInput={e => {
              const t = e.currentTarget
              t.style.height = 'auto'
              t.style.height = Math.min(t.scrollHeight, 120) + 'px'
            }}
          />
          {running ? (
            <button onClick={cancel} className="btn-stop">
              <StopCircle size={15} strokeWidth={2} /> Stop
            </button>
          ) : (
            <button onClick={send} disabled={!input.trim()} className="btn-send">
              <Send size={15} strokeWidth={2.5} /> Send
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
