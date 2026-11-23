import React from 'react'

interface ToolCallState {
  call_id: string; tool: string; args: Record<string, unknown>
  decision?: string; reason?: string
  awaitingApproval?: boolean
}

interface Props {
  toolCall: ToolCallState
  onApprove: () => void
  onDeny: () => void
}

export default function ApprovalPrompt({ toolCall, onApprove, onDeny }: Props) {
  const isDestructive = toolCall.decision === 'destructive'

  return (
    <div style={{
      background: '#1c1510', border: '1px solid #78350f', borderRadius: 8,
      padding: '0.75rem 1rem', marginBottom: '0.75rem', fontSize: '0.85rem'
    }}>
      <div style={{ color: '#fbbf24', fontWeight: 700, marginBottom: '0.4rem' }}>
        ⚠ Approval Required
      </div>
      <div style={{ color: '#ccc', marginBottom: '0.3rem' }}>
        <strong>{toolCall.tool}</strong>
        {Object.keys(toolCall.args).length > 0 && (
          <span style={{ color: '#888', marginLeft: 8 }}>
            {Object.entries(toolCall.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')}
          </span>
        )}
      </div>
      {toolCall.reason && (
        <div style={{ color: '#888', fontSize: '0.78rem', marginBottom: '0.75rem' }}>
          {toolCall.reason}
        </div>
      )}
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        {/* Approve is NOT the default for destructive actions */}
        {!isDestructive && (
          <button
            onClick={onApprove}
            style={{
              background: '#14532d', color: '#6ee7b7', border: '1px solid #166534',
              borderRadius: 6, padding: '0.4rem 1rem', cursor: 'pointer', fontWeight: 600,
            }}>
            Approve
          </button>
        )}
        <button
          onClick={onDeny}
          style={{
            background: '#1a1a1a', color: '#aaa', border: '1px solid #333',
            borderRadius: 6, padding: '0.4rem 1rem', cursor: 'pointer',
          }}>
          Deny
        </button>
        {isDestructive && (
          <button
            onClick={onApprove}
            style={{
              background: '#7f1d1d', color: '#fca5a5', border: '1px solid #991b1b',
              borderRadius: 6, padding: '0.4rem 1rem', cursor: 'pointer', fontWeight: 600,
            }}>
            Approve (destructive)
          </button>
        )}
      </div>
    </div>
  )
}
