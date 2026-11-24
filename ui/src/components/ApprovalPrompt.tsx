import React, { useState } from 'react'
import { AlertTriangle, Check, X } from 'lucide-react'
import { ToolCallState } from './ToolCallCard'

interface Props {
  toolCall: ToolCallState
  onApprove: () => Promise<void>
  onDeny: () => Promise<void>
}

export default function ApprovalPrompt({ toolCall, onApprove, onDeny }: Props) {
  const [loading, setLoading] = useState<'approve' | 'deny' | null>(null)
  const [ack, setAck] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isDestructive = toolCall.risk_tier === 'destructive'
  const args = toolCall.args || {}
  const reason = toolCall.reason || toolCall.policy_reason

  const handle = async (approved: boolean) => {
    setLoading(approved ? 'approve' : 'deny')
    setError(null)
    try {
      if (approved) await onApprove(); else await onDeny()
    } catch (e: any) {
      setError(e?.message || String(e))
      setLoading(null)
    }
  }

  return (
    <div style={{
      background: isDestructive ? '#1a0a0a' : '#16100a',
      border: `1px solid ${isDestructive ? '#7f1d1d' : '#78350f'}`, borderRadius: 8,
      padding: '0.875rem 1rem', marginBottom: '0.5rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem', flexWrap: 'wrap' }}>
        <AlertTriangle size={15} color={isDestructive ? '#fca5a5' : '#fbbf24'} strokeWidth={2} />
        <span style={{ color: isDestructive ? '#fca5a5' : '#fbbf24', fontWeight: 700, fontSize: '0.85rem' }}>
          Approval Required
        </span>
        {toolCall.risk_tier && (
          <span style={{
            fontSize: '0.65rem', padding: '1px 7px', borderRadius: 10, textTransform: 'uppercase', letterSpacing: '0.05em',
            color: isDestructive ? '#fca5a5' : '#fbbf24', border: `1px solid ${isDestructive ? '#991b1b' : '#92400e'}`,
          }}>
            {toolCall.risk_tier}
          </span>
        )}
      </div>

      {/* What, where, why */}
      <div style={{ background: '#0f0a05', borderRadius: 6, padding: '0.5rem 0.75rem', marginBottom: '0.6rem', fontSize: '0.8rem', lineHeight: 1.7 }}>
        <div>
          <span style={{ color: '#666' }}>Action </span>
          <span style={{ fontFamily: 'monospace', color: '#fbbf24' }}>{toolCall.tool}</span>
          {Object.keys(args).length > 0 && (
            <span style={{ color: '#aaa', marginLeft: 8 }}>
              {Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')}
            </span>
          )}
        </div>
        <div>
          <span style={{ color: '#666' }}>Target </span>
          <span style={{ color: toolCall.target_id ? '#c084fc' : '#ccc' }}>{toolCall.target_id || 'this machine (local)'}</span>
        </div>
        {reason && (
          <div>
            <span style={{ color: '#666' }}>Policy </span>
            <span style={{ color: '#999' }}>{reason}</span>
            {toolCall.rule_id && <span style={{ color: '#555', marginLeft: 6 }}>[{toolCall.rule_id}]</span>}
          </div>
        )}
      </div>

      {isDestructive && (
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', color: '#fca5a5', fontSize: '0.78rem', marginBottom: '0.6rem', cursor: 'pointer' }}>
          <input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />
          I understand this action is destructive
        </label>
      )}

      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button disabled={!!loading} onClick={() => handle(false)} style={{
          background: 'transparent', color: '#aaa', border: '1px solid #333',
          borderRadius: 6, padding: '0.4rem 1rem', cursor: loading ? 'not-allowed' : 'pointer',
          fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.3rem',
        }}>
          {loading === 'deny' ? <div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> : <X size={13} strokeWidth={2.5} />} Deny
        </button>

        <button disabled={!!loading || (isDestructive && !ack)} onClick={() => handle(true)} style={{
          background: isDestructive ? '#7f1d1d' : '#14532d',
          color: isDestructive ? '#fca5a5' : '#6ee7b7',
          border: `1px solid ${isDestructive ? '#991b1b' : '#166534'}`,
          borderRadius: 6, padding: '0.4rem 1rem',
          cursor: loading || (isDestructive && !ack) ? 'not-allowed' : 'pointer',
          opacity: isDestructive && !ack ? 0.5 : 1,
          fontWeight: 600, fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.3rem',
        }}>
          {loading === 'approve'
            ? <><div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Executing…</>
            : <><Check size={13} strokeWidth={2.5} /> {isDestructive ? 'Approve (destructive)' : 'Approve'}</>}
        </button>
      </div>
      {error && <div style={{ color: '#fca5a5', fontSize: '0.75rem', marginTop: '0.5rem' }}>{error}</div>}
    </div>
  )
}
