import React, { useEffect, useState } from 'react'
import { apiGet, apiPost, apiDelete } from '../api/client'

interface KBDocument {
  id: string; file_name: string; file_path: string
  status: string; error_message: string | null; chunk_count: number; updated_at: string
}

export default function KnowledgePage() {
  const [docs, setDocs] = useState<KBDocument[]>([])
  const [folder, setFolder] = useState('')
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])

  const loadDocs = () => apiGet<KBDocument[]>('/api/knowledge/documents').then(setDocs)
  useEffect(() => { loadDocs() }, [])

  const setKBFolder = async () => {
    if (!folder) return
    setLoading(true)
    try {
      await apiPost('/api/knowledge/folder', { folder })
      await loadDocs()
    } catch (e: any) {
      alert(e.message)
    } finally {
      setLoading(false)
    }
  }

  const reindex = async (id: string) => {
    await apiPost(`/api/knowledge/documents/${id}/reindex`)
    await loadDocs()
  }

  const remove = async (id: string) => {
    await apiDelete(`/api/knowledge/documents/${id}`)
    await loadDocs()
  }

  const search = async () => {
    if (!searchQuery) return
    const r = await apiPost<any>('/api/knowledge/search', { query: searchQuery, top_k: 5 })
    setSearchResults(r.results || [])
  }

  const statusColor: Record<string, string> = {
    ok: '#6ee7b7', failed: '#fca5a5', indexing: '#fbbf24', unknown: '#888'
  }

  return (
    <div style={{ padding: '2rem', maxWidth: 900, margin: '0 auto' }}>
      <h2 style={{ color: '#e5e5e5', marginBottom: '0.5rem' }}>Knowledge Base</h2>

      {/* Folder picker */}
      <div style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 8, padding: '1rem', marginBottom: '1.5rem' }}>
        <label style={{ color: '#888', fontSize: '0.85rem', display: 'block', marginBottom: '0.5rem' }}>
          Documents folder
        </label>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            value={folder}
            onChange={e => setFolder(e.target.value)}
            placeholder="e.g. C:\Documents\SOPs"
            style={{ flex: 1, background: '#0f0f0f', border: '1px solid #333', borderRadius: 6, padding: '0.5rem 0.75rem', color: '#e5e5e5', fontSize: '0.85rem' }}
          />
          <button onClick={setKBFolder} disabled={loading}
            style={{ background: '#6ee7b7', color: '#0f0f0f', border: 'none', borderRadius: 6, padding: '0.5rem 1rem', cursor: 'pointer', fontWeight: 600 }}>
            {loading ? 'Indexing…' : 'Index Folder'}
          </button>
        </div>
      </div>

      {/* Document list */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ color: '#ccc', marginBottom: '0.75rem', fontSize: '0.95rem' }}>Documents ({docs.length})</h3>
        {docs.length === 0 ? (
          <p style={{ color: '#555', fontSize: '0.85rem' }}>No documents indexed yet.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {docs.map(doc => (
              <div key={doc.id} style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 6, padding: '0.75rem 1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ color: '#e5e5e5', fontSize: '0.85rem', fontWeight: 500 }}>{doc.file_name}</div>
                  <div style={{ color: '#555', fontSize: '0.75rem' }}>{doc.file_path}</div>
                  {doc.error_message && <div style={{ color: '#fca5a5', fontSize: '0.75rem' }}>{doc.error_message}</div>}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.75rem' }}>
                  <span style={{ color: statusColor[doc.status] || '#888', textTransform: 'uppercase' }}>{doc.status}</span>
                  <span style={{ color: '#555' }}>{doc.chunk_count} chunks</span>
                  <button onClick={() => reindex(doc.id)} style={{ background: '#2a2a2a', color: '#aaa', border: 'none', borderRadius: 4, padding: '2px 8px', cursor: 'pointer' }}>Re-index</button>
                  <button onClick={() => remove(doc.id)} style={{ background: '#2a2a2a', color: '#fca5a5', border: 'none', borderRadius: 4, padding: '2px 8px', cursor: 'pointer' }}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Test search */}
      <div style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', borderRadius: 8, padding: '1rem' }}>
        <h3 style={{ color: '#ccc', marginBottom: '0.75rem', fontSize: '0.95rem' }}>Test Search</h3>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            placeholder="Search the knowledge base..."
            style={{ flex: 1, background: '#0f0f0f', border: '1px solid #333', borderRadius: 6, padding: '0.5rem 0.75rem', color: '#e5e5e5', fontSize: '0.85rem' }}
          />
          <button onClick={search} style={{ background: '#6ee7b7', color: '#0f0f0f', border: 'none', borderRadius: 6, padding: '0.5rem 1rem', cursor: 'pointer', fontWeight: 600 }}>Search</button>
        </div>
        {searchResults.map((r, i) => (
          <div key={i} style={{ background: '#0f0f0f', borderRadius: 6, padding: '0.75rem', marginBottom: '0.5rem', fontSize: '0.8rem' }}>
            <div style={{ color: '#6ee7b7', marginBottom: '0.3rem' }}>{r.document} {r.heading_path && `· ${r.heading_path}`}</div>
            <div style={{ color: '#ccc', lineHeight: 1.5 }}>{r.content.slice(0, 300)}…</div>
            <div style={{ color: '#555', marginTop: '0.3rem' }}>score: {r.score}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
