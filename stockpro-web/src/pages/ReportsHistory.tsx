import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import toast from 'react-hot-toast'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'

type View = 'tickers' | 'list'

export default function ReportsHistory() {
  const [view, setView] = useState<View>('tickers')
  const [search, setSearch] = useState('')
  const api = useApiClient()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['reports'],
    queryFn: async () => {
      const res = await api.get('/api/reports')
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

  const reportsRaw: any[] = data?.reports || []

  // Group reports by ticker
  const tickerMap: Record<string, { reports: any[]; latestDate: string }> = {}
  for (const r of reportsRaw) {
    const sym = (r.ticker || r.symbol || '?').toUpperCase()
    if (!tickerMap[sym]) tickerMap[sym] = { reports: [], latestDate: '' }
    tickerMap[sym].reports.push(r)
    const d = r.created_at ? new Date(r.created_at).toISOString() : ''
    if (!tickerMap[sym].latestDate || d > tickerMap[sym].latestDate) {
      tickerMap[sym].latestDate = d
    }
  }

  // Sort tickers by most recent report
  const tickers = Object.entries(tickerMap)
    .sort((a, b) => (b[1].latestDate > a[1].latestDate ? 1 : -1))
    .filter(([sym]) => !search || sym.toLowerCase().includes(search.toLowerCase()))

  const reports = reportsRaw
    .filter(r => {
      const sym = (r.ticker || r.symbol || '').toUpperCase()
      return !search || sym.toLowerCase().includes(search.toLowerCase()) || (r.title || '').toLowerCase().includes(search.toLowerCase())
    })
    .map((r: any) => ({
      id: r.report_id || r.id,
      symbol: (r.ticker || r.symbol || '?').toUpperCase(),
      title: r.title || `${r.ticker || ''} Research Report`,
      type: r.trade_type || r.type || '',
      created_at: r.created_at ? new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '',
    }))

  const totalTickers = Object.keys(tickerMap).length

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1000, margin: '0 auto', padding: '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
          <div>
            <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>Research Reports</div>
            <div style={{ fontSize: 13, color: '#a8a29e' }}>
              {reportsRaw.length} reports &nbsp;&middot;&nbsp; {totalTickers} tickers researched
            </div>
          </div>
          <Link
            to="/research"
            style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '9px 18px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}
          >
            <Icon name="auto_awesome" size={16} />
            New Research
          </Link>
        </div>

        {/* SEARCH + VIEW TOGGLE */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}>
          <div style={{ flex: 1, background: '#1c1917', border: '1px solid #292524', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 8, padding: '0 14px', height: 38 }}>
            <Icon name="search" size={16} style={{ color: '#a8a29e' }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={view === 'tickers' ? 'Search tickers...' : 'Search reports by ticker or keyword...'}
              style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontFamily: 'Inter, sans-serif', fontSize: 13.5, color: '#fafaf9' }}
            />
          </div>
          <div style={{ display: 'flex', background: '#1c1917', border: '1px solid #292524', borderRadius: 8, overflow: 'hidden' }}>
            {(['tickers', 'list'] as View[]).map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                style={{ padding: '7px 14px', border: 'none', cursor: 'pointer', fontSize: 12.5, fontWeight: 500, background: view === v ? 'rgba(214,211,209,0.1)' : 'transparent', color: view === v ? '#fafaf9' : '#a8a29e', display: 'flex', alignItems: 'center', gap: 5, transition: 'all 0.15s' }}
              >
                <Icon name={v === 'tickers' ? 'grid_view' : 'format_list_bulleted'} size={15} />
                {v === 'tickers' ? 'Tickers' : 'All Reports'}
              </button>
            ))}
          </div>
        </div>

        {isLoading ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} style={{ height: 100, background: '#1c1917', border: '1px solid #292524', borderRadius: 14 }} />
            ))}
          </div>
        ) : reportsRaw.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '80px 0', color: '#a8a29e' }}>
            <Icon name="description" size={48} />
            <div style={{ fontSize: 16, fontWeight: 600, marginTop: 16, color: '#fafaf9' }}>No reports yet</div>
            <div style={{ fontSize: 13, marginTop: 8 }}>Start by researching a ticker</div>
            <Link to="/research" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 20, background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '10px 20px', borderRadius: 8, textDecoration: 'none' }}>
              <Icon name="search" size={16} /> Start Research
            </Link>
          </div>
        ) : view === 'tickers' ? (
          /* TICKER GRID */
          tickers.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#a8a29e', fontSize: 14 }}>No tickers match your search</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
              {tickers.map(([sym, info]) => {
                const latestFormatted = info.latestDate
                  ? new Date(info.latestDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                  : ''
                return (
                  <div
                    key={sym}
                    onClick={() => navigate(`/ticker/${sym}`)}
                    style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: '20px', cursor: 'pointer', transition: 'border-color 0.2s, background 0.2s' }}
                    onMouseEnter={e => {
                      ;(e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(214,211,209,0.25)'
                      ;(e.currentTarget as HTMLDivElement).style.background = '#232120'
                    }}
                    onMouseLeave={e => {
                      ;(e.currentTarget as HTMLDivElement).style.borderColor = '#292524'
                      ;(e.currentTarget as HTMLDivElement).style.background = '#1c1917'
                    }}
                  >
                    <div style={{ width: 44, height: 44, borderRadius: 12, background: '#292524', border: '1px solid #333', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 14 }}>
                      <span style={{ fontFamily: 'Nunito, sans-serif', fontSize: sym.length > 4 ? 11 : 13, fontWeight: 700, color: '#d6d3d1' }}>{sym.slice(0, 5)}</span>
                    </div>
                    <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 20, fontWeight: 700, letterSpacing: '-0.01em', marginBottom: 4 }}>{sym}</div>
                    <div style={{ fontSize: 12, color: '#a8a29e', marginBottom: 2 }}>
                      {info.reports.length} {info.reports.length === 1 ? 'report' : 'reports'}
                    </div>
                    {latestFormatted && (
                      <div style={{ fontSize: 11, color: '#6b6663' }}>Last: {latestFormatted}</div>
                    )}
                  </div>
                )
              })}
            </div>
          )
        ) : (
          /* ALL REPORTS LIST */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {reports.map((r: any) => (
              <div key={r.id} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '20px 24px' }}>
                  <div
                    onClick={() => navigate(`/ticker/${r.symbol}`)}
                    style={{ width: 44, height: 44, borderRadius: 12, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, cursor: 'pointer' }}
                  >
                    <span style={{ fontFamily: 'Nunito, sans-serif', fontSize: 11, fontWeight: 700, color: '#d6d3d1' }}>{r.symbol.slice(0, 5)}</span>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Link to={`/report/${r.id}`} style={{ fontSize: 15, fontWeight: 600, color: '#fafaf9', textDecoration: 'none', display: 'block', marginBottom: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.title}
                    </Link>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span
                        onClick={() => navigate(`/ticker/${r.symbol}`)}
                        style={{ fontSize: 12, fontWeight: 600, color: '#d6d3d1', cursor: 'pointer' }}
                      >
                        {r.symbol}
                      </span>
                      {r.type && (
                        <span style={{ fontSize: 11.5, fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: 'rgba(214,211,209,0.08)', color: '#d6d3d1', border: '1px solid rgba(214,211,209,0.2)' }}>
                          {r.type}
                        </span>
                      )}
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
                      onClick={() => { if (confirm('Delete this report?')) deleteMutation.mutate(r.id) }}
                      style={{ width: 34, height: 34, borderRadius: 8, border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.05)', color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                      <Icon name="delete" size={16} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
