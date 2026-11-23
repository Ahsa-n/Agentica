import React, { useState } from 'react'

interface ToolCallState {
  call_id: string; tool: string; args: Record<string, unknown>
  decision?: string; reason?: string; rule_id?: string
  result?: unknown; duration_ms?: number
  awaitingApproval?: boolean
}

const DECISION_BADGE: Record<string, { bg: string; color: string; label: string }> = {
  allow:   { bg: '#14532d', color: '#6ee7b7', label: 'Allowed' },
  confirm: { bg: '#78350f', color: '#fbbf24', label: 'Confirm' },
  deny:    { bg: '#7f1d1d', color: '#fca5a5', label: 'Denied' },
}

export default function ToolCallCard({ toolCall }: { toolCall: ToolCallState }) {
  const [expanded, setExpanded] = useState(false)
  const badge = DECISION_BADGE[toolCall.decision || ''] || { bg: '#1a1a1a', color: '#888', label: toolCall.decision || '…' }

  return (
    <div style={{ background: '#161616', border: '1px solid #2a2a2a', borderRadius: 8, marginBottom: '0.5rem', fontSize: '0.8rem' }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{ padding: '0.5rem 0.75rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
      >
        <span style={{ color: '#888' }}>⚙</span>
        <span style={{ color: '#ccc', fontWeight: 600 }}>{toolCall.tool}</span>
        {toolCall.decision && (
          <span style={{ background: badge.bg, color: badge.color, padding: '1px 6px', borderRadius: 4, fontSize: '0.7rem', marginLeft: 4 }}>
            {badge.label}
          </span>
        )}
        {toolCall.awaitingApproval && (
          <span style={{ background: '#1e3a5f', color: '#60a5fa', padding: '1px 6px', borderRadius: 4, fontSize: '0.7rem', marginLeft: 4 }}>
            Awaiting Approval
          </span>
        )}
        {toolCall.duration_ms != null && (
          <span style={{ color: '#555', marginLeft: 'auto' }}>{Math.round(toolCall.duration_ms)}ms</span>
        )}
        <span style={{ color: '#555' }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div style={{ borderTop: '1px solid #2a2a2a', padding: '0.75rem' }}>
          {Object.keys(toolCall.args).length > 0 && (
            <div style={{ marginBottom: '0.5rem' }}>
              <span style={{ color: '#888', marginRight: 8 }}>Args:</span>
              <code style={{ color: '#fbbf24', fontSize: '0.75rem' }}>
                {JSON.stringify(toolCall.args, null, 2)}
              </code>
            </div>
          )}
          {toolCall.reason && (
            <div style={{ marginBottom: '0.5rem', color: '#888' }}>
              <span>Policy: </span>
              <span style={{ color: '#ccc' }}>{toolCall.reason}</span>
              {toolCall.rule_id && <span style={{ color: '#555', marginLeft: 8 }}>[{toolCall.rule_id}]</span>}
            </div>
          )}
          {toolCall.result != null && (
            <div>
              <span style={{ color: '#888' }}>Result:</span>
              <pre style={{
                margin: '0.5rem 0 0', padding: '0.5rem', background: '#0f0f0f',
                borderRadius: 4, overflow: 'auto', maxHeight: 300,
                color: '#6ee7b7', fontSize: '0.72rem'
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
