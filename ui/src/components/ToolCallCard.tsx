import React, { useState } from 'react'
import {
  Wrench, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp,
  Search, Cpu, Server, Network, FileText, Terminal
} from 'lucide-react'

export interface ToolCallState {
  call_id: string; tool: string; args: Record<string, unknown>
  decision?: string; reason?: string; rule_id?: string
  result?: unknown; duration_ms?: number
  awaitingApproval?: boolean
  approval?: 'approved' | 'denied'
  target_id?: string | null
  risk_tier?: 'read' | 'modify' | 'destructive' | null
  policy_reason?: string
}

const TOOL_ICONS: Record<string, React.ReactNode> = {
  search_knowledge_base: <Search size={13} strokeWidth={2} />,
  get_cpu_usage:         <Cpu size={13} strokeWidth={2} />,
  get_memory_usage:      <Cpu size={13} strokeWidth={2} />,
  get_disk_usage:        <Terminal size={13} strokeWidth={2} />,
  get_top_processes:     <Cpu size={13} strokeWidth={2} />,
  get_service_status:    <Server size={13} strokeWidth={2} />,
  restart_service:       <Server size={13} strokeWidth={2} />,
  start_service:         <Server size={13} strokeWidth={2} />,
  stop_service:          <Server size={13} strokeWidth={2} />,
  get_logs:              <FileText size={13} strokeWidth={2} />,
  check_port:            <Network size={13} strokeWidth={2} />,
}

const DECISION_STYLES: Record<string, { bg: string; color: string; border: string; label: string }> = {
  allow:   { bg: 'rgba(20,83,45,0.5)',   color: '#6ee7b7', border: '#166534', label: 'Allowed'    },
  confirm: { bg: 'rgba(120,53,15,0.5)',  color: '#fbbf24', border: '#92400e', label: 'Confirm'    },
  deny:    { bg: 'rgba(127,29,29,0.5)',  color: '#fca5a5', border: '#991b1b', label: 'Denied'     },
}

export default function ToolCallCard({ toolCall: raw }: { toolCall: ToolCallState }) {
  const toolCall = { ...raw, args: raw.args || {} }
  const [expanded, setExpanded] = useState(false)
  const badge = DECISION_STYLES[toolCall.decision || '']
  const Icon = TOOL_ICONS[toolCall.tool] ?? <Wrench size={13} strokeWidth={2} />

  const isSuccess = toolCall.result != null && !toolCall.awaitingApproval
  const errorText: string | undefined = (toolCall.result as any)?.error
  const isFailed = (toolCall.result as any)?.success === false || !!errorText

  return (
    <div style={{
      background: '#111', border: '1px solid #1e1e1e', borderRadius: 8,
      marginBottom: '0.4rem', fontSize: '0.8rem', overflow: 'hidden',
    }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          padding: '0.45rem 0.75rem', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          userSelect: 'none',
        }}
      >
        <span style={{ color: '#555', flexShrink: 0, display: 'flex' }}>{Icon}</span>
        <span style={{ color: '#bbb', fontWeight: 500, fontFamily: 'monospace', fontSize: '0.78rem' }}>
          {toolCall.tool}
        </span>
        <span title={toolCall.target_id ? 'Ran on a remote machine' : 'Ran on this machine'} style={{
          color: toolCall.target_id ? '#c084fc' : '#555', border: `1px solid ${toolCall.target_id ? '#7c3aed55' : '#2a2a2a'}`,
          padding: '0 6px', borderRadius: 10, fontSize: '0.65rem', flexShrink: 0,
        }}>
          {toolCall.target_id ? `on ${toolCall.target_id}` : 'local'}
        </span>

        {/* Args preview */}
        {Object.keys(toolCall.args).length > 0 && !expanded && (
          <span style={{ color: '#555', fontSize: '0.72rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 180 }}>
            ({Object.entries(toolCall.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})
          </span>
        )}

        {/* Decision badge */}
        {badge && (
          <span style={{
            background: badge.bg, color: badge.color, border: `1px solid ${badge.border}`,
            padding: '1px 7px', borderRadius: 10, fontSize: '0.65rem', fontWeight: 600,
            flexShrink: 0, marginLeft: 2,
          }}>
            {badge.label}
          </span>
        )}

        {/* Awaiting */}
        {toolCall.awaitingApproval && (
          <span style={{
            background: 'rgba(30,58,138,0.5)', color: '#93c5fd', border: '1px solid #1e40af',
            padding: '1px 7px', borderRadius: 10, fontSize: '0.65rem', flexShrink: 0,
          }}>
            Awaiting Approval
          </span>
        )}

        {/* Human decision */}
        {toolCall.approval && (
          <span style={{
            background: 'transparent', color: toolCall.approval === 'approved' ? '#6ee7b7' : '#fca5a5',
            border: `1px solid ${toolCall.approval === 'approved' ? '#166534' : '#991b1b'}`,
            padding: '1px 7px', borderRadius: 10, fontSize: '0.65rem', flexShrink: 0,
          }}>
            {toolCall.approval === 'approved' ? 'Approved by you' : 'Denied by you'}
          </span>
        )}

        {/* Result status */}
        {isSuccess && !toolCall.awaitingApproval && (
          isFailed
            ? <XCircle size={13} color="#fca5a5" strokeWidth={2} style={{ flexShrink: 0, marginLeft: 2 }} />
            : <CheckCircle size={13} color="#6ee7b7" strokeWidth={2} style={{ flexShrink: 0, marginLeft: 2 }} />
        )}

        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#444' }}>
          {toolCall.duration_ms != null && (
            <span style={{ display: 'flex', alignItems: 'center', gap: '2px', fontSize: '0.68rem' }}>
              <Clock size={10} strokeWidth={2} />
              {Math.round(toolCall.duration_ms)}ms
            </span>
          )}
          {expanded ? <ChevronUp size={12} strokeWidth={2} /> : <ChevronDown size={12} strokeWidth={2} />}
        </span>
      </div>

      {/* Error is shown without expanding, so failures are never hidden */}
      {errorText && !expanded && (
        <div style={{ borderTop: '1px solid #1e1e1e', padding: '0.4rem 0.75rem', color: '#fca5a5', fontSize: '0.74rem', overflowWrap: 'anywhere' }}>
          {errorText}
        </div>
      )}

      {/* Expanded */}
      {expanded && (
        <div style={{ borderTop: '1px solid #1e1e1e', padding: '0.6rem 0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {Object.keys(toolCall.args).length > 0 && (
            <div>
              <span style={{ color: '#555', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Arguments</span>
              <pre style={{ margin: '0.3rem 0 0', padding: '0.5rem', background: '#0a0a0a', borderRadius: 5, color: '#fbbf24', fontSize: '0.72rem', overflow: 'auto', maxHeight: 120 }}>
                {JSON.stringify(toolCall.args, null, 2)}
              </pre>
            </div>
          )}

          {toolCall.reason && (
            <div style={{ color: '#555', fontSize: '0.75rem' }}>
              <span style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontSize: '0.7rem' }}>Policy </span>
              <span style={{ color: '#888' }}>{toolCall.reason}</span>
              {toolCall.rule_id && <span style={{ color: '#3a3a3a', marginLeft: 6 }}>[{toolCall.rule_id}]</span>}
            </div>
          )}

          {toolCall.result != null && (
            <div>
              <span style={{ color: '#555', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Result</span>
              <pre style={{
                margin: '0.3rem 0 0', padding: '0.5rem', background: '#0a0a0a', borderRadius: 5,
                color: '#6ee7b7', fontSize: '0.72rem', overflow: 'auto', maxHeight: 280,
              }}>
                {JSON.stringify(toolCall.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
