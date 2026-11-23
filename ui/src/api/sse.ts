/**
 * SSE helper — wraps fetchEventSource with auth token and typed events.
 */
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { getToken } from './client'

export type SSEEvent =
  | { type: 'run_start'; data: { session_id: string } }
  | { type: 'route'; data: { categories: string[] } }
  | { type: 'policy_decision'; data: { call_id: string; tool: string; decision: string; reason: string; rule_id: string } }
  | { type: 'tool_start'; data: { call_id: string; tool: string; args: Record<string, unknown> } }
  | { type: 'tool_end'; data: { call_id: string; tool: string; duration_ms: number; result: unknown } }
  | { type: 'approval_required'; data: { call_id: string; tool: string; args: Record<string, unknown>; target_id: string | null; policy_reason: string } }
  | { type: 'verify'; data: { call_id: string; success: boolean } }
  | { type: 'token'; data: { text: string } }
  | { type: 'final'; data: { answer: string } }
  | { type: 'run_end'; data: Record<string, never> }
  | { type: 'error'; data: { message: string } }

export interface StreamOptions {
  sessionId: string
  content: string
  routingMode?: string
  forceCategories?: string[]
  onEvent: (evt: SSEEvent) => void
  onDone: () => void
  signal?: AbortSignal
}

export async function streamMessage(opts: StreamOptions): Promise<void> {
  const token = await getToken()
  await fetchEventSource(`/api/sessions/${opts.sessionId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      content: opts.content,
      routing_mode: opts.routingMode ?? 'routed',
      force_categories: opts.forceCategories ?? [],
    }),
    signal: opts.signal,
    onmessage(msg) {
      if (!msg.event || msg.event === 'message') return
      try {
        const data = JSON.parse(msg.data)
        opts.onEvent({ type: msg.event as SSEEvent['type'], data } as SSEEvent)
      } catch {
        // ignore parse errors
      }
    },
    onclose() {
      opts.onDone()
    },
    onerror(err) {
      opts.onEvent({ type: 'error', data: { message: String(err) } })
    },
  })
}
