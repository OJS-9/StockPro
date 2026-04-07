import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import toast from 'react-hot-toast'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'

const FILTERS = ['All', 'Day Trade', 'Swing Trade', 'Investment']

const typeColors: Record<string, { bg: string; color: string; border: string }> = {
  'Day Trade': { bg: 'rgba(34,197,94,0.08)', color: '#22c55e', border: 'rgba(34,197,94,0.2)' },
  'Swing Trade': { bg: 'rgba(214,211,209,0.08)', color: '#d6d3d1', border: 'rgba(214,211,209,0.2)' },
  'Investment': { bg: 'rgba(96,165,250,0.08)', color: '#60a5fa', border: 'rgba(96,165,250,0.2)' },
}

export default function ReportsHistory() {
  const [filter, setFilter] = useState('All')
  const api = useApiClient()
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['reports', filter],
    queryFn: async () => {
      const q = filter !== 'All' ? `?trade_type=${encodeURIComponent(filter)}` : ''
      const res = await api.get(`/api/reports${q}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.delete(`/api/reports/${id}`)
      if (!res.ok) throw new Error('Failed')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      toast.success('Report deleted')
    },
    onError: () => toast.error('Failed to delete report'),
  })

  // API fields: report_id, ticker, trade_type, created_at (ISO string), title (may be absent)
  const reportsRaw = data?.reports || []
  const reports = reportsRaw.map((r: any) => ({
    id: r.report_id || r.id,
    symbol: r.ticker || r.symbol || '?',
    title: r.title || `${r.ticker || ''} Research Report`,
    type: r.trade_type || r.type || '',
    created_at: r.created_at ? new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '',
    subjects: r.subjects_count || r.subjects || null,
  }))

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1000, margin: '0 auto', padding: '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32 }}>
          <div>
            <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>Research Reports</div>
            <div style={{ fontSize: 13, color: '#a8a29e' }}>{reports.length} reports</div>
          </div>
          <Link
            to="/research"
            style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}
          >
            <Icon name="add" size={16} />
            New Research
          </Link>
        </div>

        {/* FILTER TABS */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 24 }}>
          {FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{ padding: '7px 16px', borderRadius: 8, fontSize: 13, fontWeight: 500, border: 'none', cursor: 'pointer', background: filter === f ? 'rgba(214,211,209,0.1)' : 'transparent', color: filter === f ? '#fafaf9' : '#a8a29e', transition: 'all 0.15s' }}
            >
              {f}
            </button>
          ))}
        </div>

        {/* REPORTS LIST */}
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[1, 2, 3].map(i => <div key={i} style={{ height: 100, background: '#1c1917', border: '1px solid #292524', borderRadius: 14 }} />)}
          </div>
        ) : reports.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '80px 0', color: '#a8a29e' }}>
            <Icon name="description" size={48} />
            <div style={{ fontSize: 16, fontWeight: 600, marginTop: 16, color: '#fafaf9' }}>No reports yet</div>
            <div style={{ fontSize: 13, marginTop: 8 }}>Start by researching a ticker</div>
            <Link to="/research" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 20, background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '10px 20px', borderRadius: 8, textDecoration: 'none' }}>
              <Icon name="search" size={16} /> Start Research
            </Link>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {reports.map((r: any) => {
              const tc = typeColors[r.type] || typeColors['Investment']
              return (
                <div key={r.id} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden', transition: 'border-color 0.2s' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '20px 24px' }}>
                    <div style={{ width: 44, height: 44, borderRadius: 12, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <span style={{ fontFamily: 'Nunito, sans-serif', fontSize: 13, fontWeight: 700, color: '#d6d3d1' }}>{r.symbol}</span>
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Link to={`/report/${r.id}`} style={{ fontSize: 15, fontWeight: 600, color: '#fafaf9', textDecoration: 'none', display: 'block', marginBottom: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.title}
                      </Link>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 11.5, fontWeight: 500, padding: '3px 8px', borderRadius: 999, background: tc.bg, color: tc.color, border: `1px solid ${tc.border}` }}>
                          {r.type}
                        </span>
                        <span style={{ fontSize: 12, color: '#a8a29e' }}>{r.subjects ? `${r.subjects} research subjects` : ''}</span>
                        <span style={{ fontSize: 12, color: '#a8a29e' }}>{r.created_at}</span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                      <Link
                        to={`/chat/${r.id}`}
                        style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 12.5, fontWeight: 500, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 5 }}
                      >
                        <Icon name="forum" size={14} /> Chat
                      </Link>
                      <Link
                        to={`/report/${r.id}`}
                        style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 12.5, fontWeight: 500, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 5 }}
                      >
                        <Icon name="open_in_new" size={14} /> View
                      </Link>
                      <button
                        onClick={() => {
                          if (confirm('Delete this report?')) deleteMutation.mutate(r.id)
                        }}
                        style={{ width: 34, height: 34, borderRadius: 8, border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.05)', color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                      >
                        <Icon name="delete" size={16} />
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </main>
    </div>
  )
}
