/**
 * API client — fetches token on first call, includes Bearer on all requests.
 * SSE streaming via @microsoft/fetch-event-source.
 */

let _token: string | null = null

async function getToken(): Promise<string> {
  if (_token) return _token
  const resp = await fetch('/api/token')
  const data = await resp.json()
  _token = data.token
  return _token!
}

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = await getToken()
  return fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  })
}

export async function apiGet<T>(path: string): Promise<T> {
  const resp = await apiFetch(path)
  if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
  return resp.json()
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const resp = await apiFetch(path, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
  return resp.json()
}

export async function apiDelete<T>(path: string): Promise<T> {
  const resp = await apiFetch(path, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
  return resp.json()
}

export { apiFetch, getToken }
