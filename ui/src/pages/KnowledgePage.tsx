import React, { useEffect, useState } from 'react'
import { RefreshCw, Trash2, Search, FolderOpen, FileText, AlertCircle, CheckCircle } from 'lucide-react'
import { apiGet, apiPost, apiDelete } from '../api/client'

interface KBDocument {
  id: string; file_name: string; file_path: string
  status: string; error_message: string | null; chunk_count: number; updated_at: string
}

interface SearchResult {
  document: string; heading_path: string | null; content: string; score: number
}

export default function KnowledgePage() {
  const [docs, setDocs] = useState<KBDocument[]>([])
  const [folder, setFolder] = useState('')
  const [loading, setLoading] = useState(false)
  const [docsLoading, setDocsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [flashMsg, setFlashMsg] = useState<{ text: string; ok: boolean } | null>(null)

  const loadDocs = async () => {
    setDocsLoading(true)
    try {
      const data = await apiGet<KBDocument[]>('/api/knowledge/documents')
      setDocs(data)
    } finally {
      setDocsLoading(false)
    }
  }

  const [watched, setWatched] = useState<{ folder: string | null; watching: boolean } | null>(null)
  const loadFolder = async () => {
    try {
      const f = await apiGet<{ folder: string | null; watching: boolean }>('/api/knowledge/folder')
      setWatched(f)
      if (f.folder) setFolder(prev => prev || f.folder!)
    } catch { /* backend offline */ }
  }

  useEffect(() => { loadDocs(); loadFolder() }, [])

  const flash = (text: string, ok: boolean) => {
    setFlashMsg({ text, ok })
    setTimeout(() => setFlashMsg(null), 3000)
  }

  const setKBFolder = async () => {
    if (!folder.trim()) return
    setLoading(true)
    try {
      const r = await apiPost<{ documents: number }>('/api/knowledge/folder', { folder: folder.trim() })
      await Promise.all([loadDocs(), loadFolder()])
      flash(`Indexed ${r.documents} document(s)`, true)
    } catch (e: any) {
      flash(e.message || 'Failed to index folder', false)
    } finally {
      setLoading(false)
    }
  }

  const reindex = async (id: string) => {
    try {
      await apiPost(`/api/knowledge/documents/${id}/reindex`)
      await loadDocs()
      flash('Re-indexed', true)
    } catch (e: any) {
      flash(e.message, false)
    }
  }

  const remove = async (id: string) => {
    await apiDelete(`/api/knowledge/documents/${id}`)
    setDocs(prev => prev.filter(d => d.id !== id))
  }

  const search = async () => {
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const r = await apiPost<{ results: SearchResult[] }>('/api/knowledge/search', { query: searchQuery.trim(), top_k: 5 })
      setSearchResults(r.results || [])
    } finally {
      setSearching(false)
    }
  }

  const statusStyles: Record<string, { color: string; icon: React.ReactNode }> = {
    ok:       { color: '#6ee7b7', icon: <CheckCircle size={13} strokeWidth={2} color="#6ee7b7" /> },
    failed:   { color: '#fca5a5', icon: <AlertCircle size={13} strokeWidth={2} color="#fca5a5" /> },
    indexing: { color: '#fbbf24', icon: <div className="spinner" style={{ width: 12, height: 12, borderWidth: 1 }} /> },
  }

  const okDocs = docs.filter(d => d.status === 'ok')
  const totalChunks = okDocs.reduce((s, d) => s + (d.chunk_count || 0), 0)

  return (
    <div className="page-pad" style={{ maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '1rem', marginBottom: '1.5rem' }}>
        <h2 style={{ color: '#fff', margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>Knowledge Base</h2>
        {docs.length > 0 && (
          <span style={{ color: '#555', fontSize: '0.8rem' }}>
            {okDocs.length} docs · {totalChunks} chunks
          </span>
        )}
      </div>

      {/* Flash message */}
      {flashMsg && (
        <div style={{
          background: flashMsg.ok ? 'rgba(20,83,45,0.4)' : 'rgba(127,29,29,0.4)',
          border: `1px solid ${flashMsg.ok ? '#166534' : '#991b1b'}`,
          borderRadius: 7, padding: '0.6rem 1rem', marginBottom: '1rem',
          fontSize: '0.85rem', color: flashMsg.ok ? '#6ee7b7' : '#fca5a5',
        }}>
          {flashMsg.text}
        </div>
      )}

      {/* Folder picker */}
      <div style={{ background: '#111', border: '1px solid #1e1e1e', borderRadius: 10, padding: '1rem', marginBottom: '1.5rem' }}>
        <label style={{ color: '#666', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: '0.5rem' }}>
          Index a folder
        </label>
        <div className="kb-row" style={{ display: 'flex', gap: '0.5rem' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
            <FolderOpen size={14} color="#444" strokeWidth={1.8} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
            <input
              value={folder}
              onChange={e => setFolder(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && setKBFolder()}
              placeholder="e.g. D:\Documents\SOPs"
              style={{
                width: '100%', background: '#0a0a0a', border: '1px solid #2a2a2a', borderRadius: 7,
                padding: '0.55rem 0.75rem 0.55rem 2rem', color: '#e5e5e5', fontSize: '0.85rem',
                boxSizing: 'border-box',
              }}
            />
          </div>
          <button
            onClick={setKBFolder}
            disabled={loading || !folder.trim()}
            style={{
              background: loading ? '#1a1a1a' : '#6ee7b7', color: loading ? '#555' : '#0a0a0a',
              border: 'none', borderRadius: 7, padding: '0.55rem 1.1rem',
              cursor: loading ? 'not-allowed' : 'pointer', fontWeight: 600, fontSize: '0.85rem',
              display: 'flex', alignItems: 'center', gap: '0.4rem', flexShrink: 0,
            }}>
            {loading ? <><div className="spinner" style={{ width: 13, height: 13, borderWidth: 2 }} /> Indexing…</> : 'Index Folder'}
          </button>
        </div>
        <p style={{ margin: '0.6rem 0 0', color: '#444', fontSize: '0.75rem' }}>
          Supported: .md .txt .pdf .docx .html — new, changed and deleted files are re-indexed automatically
        </p>
        {watched?.folder && (
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.75rem', color: watched.watching ? '#6ee7b7' : '#fbbf24', overflowWrap: 'anywhere' }}>
            {watched.watching ? '● Watching ' : '○ Saved folder (watcher starting) '}
            <code style={{ background: '#1a1a1a', padding: '1px 5px', borderRadius: 4 }}>{watched.folder}</code>
          </p>
        )}
      </div>

      {/* Document list */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <h3 style={{ color: '#888', margin: 0, fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            Documents
          </h3>
          <button
            onClick={loadDocs}
            className="icon-btn"
            style={{ background: 'none', border: 'none', color: '#444', cursor: 'pointer', padding: '3px', borderRadius: 4, display: 'flex' }}>
            <RefreshCw size={13} strokeWidth={2} />
          </button>
        </div>

        {docsLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#555', fontSize: '0.85rem', padding: '1rem 0' }}>
            <div className="spinner" /> Loading…
          </div>
        ) : docs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#3a3a3a', border: '1px dashed #1e1e1e', borderRadius: 10 }}>
            <FileText size={28} strokeWidth={1.2} style={{ marginBottom: '0.5rem', display: 'block', margin: '0 auto 0.5rem' }} />
            <p style={{ margin: 0, fontSize: '0.85rem' }}>No documents indexed yet. Enter a folder path above.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {docs.map(doc => {
              const st = statusStyles[doc.status] || { color: '#888', icon: null }
              return (
                <div key={doc.id} className="card-hover" style={{
                  background: '#111', border: '1px solid #1e1e1e', borderRadius: 8,
                  padding: '0.65rem 1rem', display: 'flex', alignItems: 'center', gap: '0.75rem',
                }}>
                  <span style={{ display: 'flex', flexShrink: 0 }}>{st.icon}</span>
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ color: '#ddd', fontSize: '0.85rem', fontWeight: 500 }}>{doc.file_name}</div>
                    <div style={{ color: '#3a3a3a', fontSize: '0.72rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {doc.file_path}
                    </div>
                    {doc.error_message && (
                      <div style={{ color: '#fca5a5', fontSize: '0.72rem' }}>{doc.error_message}</div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexShrink: 0 }}>
                    <span style={{ color: '#3a3a3a', fontSize: '0.72rem' }}>{doc.chunk_count} chunks</span>
                    <button
                      onClick={() => reindex(doc.id)}
                      className="icon-btn"
                      title="Re-index"
                      style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', color: '#666', borderRadius: 5, padding: '3px 6px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                      <RefreshCw size={12} strokeWidth={2} />
                    </button>
                    <button
                      onClick={() => remove(doc.id)}
                      className="icon-btn"
                      title="Remove"
                      style={{ background: '#1a1a1a', border: '1px solid #2a2a2a', color: '#666', borderRadius: 5, padding: '3px 6px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                      <Trash2 size={12} strokeWidth={2} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Search test */}
      <div style={{ background: '#111', border: '1px solid #1e1e1e', borderRadius: 10, padding: '1rem' }}>
        <h3 style={{ color: '#888', margin: '0 0 0.75rem', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          Test Hybrid Search
        </h3>
        <div className="kb-row" style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.875rem' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
            <Search size={14} color="#444" strokeWidth={1.8} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && search()}
              placeholder="e.g. nginx restart procedure"
              style={{
                width: '100%', background: '#0a0a0a', border: '1px solid #2a2a2a', borderRadius: 7,
                padding: '0.55rem 0.75rem 0.55rem 2rem', color: '#e5e5e5', fontSize: '0.85rem',
                boxSizing: 'border-box',
              }}
            />
          </div>
          <button
            onClick={search}
            disabled={searching || !searchQuery.trim()}
            style={{
              background: '#6ee7b7', color: '#0a0a0a', border: 'none', borderRadius: 7,
              padding: '0.55rem 1.1rem', cursor: 'pointer', fontWeight: 600, fontSize: '0.85rem',
              display: 'flex', alignItems: 'center', gap: '0.4rem', flexShrink: 0,
            }}>
            {searching ? <div className="spinner" style={{ width: 13, height: 13, borderWidth: 2 }} /> : <Search size={14} strokeWidth={2.5} />}
            Search
          </button>
        </div>

        {searchResults.length === 0 && searchQuery && !searching && (
          <p style={{ color: '#444', fontSize: '0.82rem', textAlign: 'center', padding: '1rem 0' }}>No results found.</p>
        )}

        {searchResults.map((r, i) => (
          <div key={i} style={{
            background: '#0a0a0a', borderRadius: 7, padding: '0.75rem',
            marginBottom: '0.5rem', border: '1px solid #1a1a1a',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <span style={{ color: '#6ee7b7', fontSize: '0.78rem', fontWeight: 500 }}>
                {r.document}{r.heading_path ? ` › ${r.heading_path}` : ''}
              </span>
              <span style={{ color: '#3a3a3a', fontSize: '0.72rem' }}>score {r.score.toFixed(4)}</span>
            </div>
            <p style={{ margin: 0, color: '#888', fontSize: '0.8rem', lineHeight: 1.6 }}>
              {r.content.slice(0, 320)}{r.content.length > 320 ? '…' : ''}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
