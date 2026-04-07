import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'

const fmt = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)

function LineChart({ data, costBasis, gain = true }: { data: number[]; costBasis?: number[]; gain?: boolean }) {
  if (!data || data.length < 2) return <div style={{ height: 160, background: '#232120', borderRadius: 8 }} />
  const color = gain ? '#22c55e' : '#ef4444'
  const all = [...data, ...(costBasis || [])]
  const min = Math.min(...all); const max = Math.max(...all)
  const range = max - min || 1
  const w = 600; const h = 160; const pad = 12

  const toPath = (arr: number[]) => arr.map((v, i) => {
    const x = pad + (i / (arr.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x},${y}`
  }).join(' ')

  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" fill="none" style={{ width: '100%', height: 160 }}>
      <defs>
        <linearGradient id="analGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Cost basis dashed line */}
      {costBasis && costBasis.length > 1 && (
        <polyline points={toPath(costBasis)} stroke="#a8a29e" strokeWidth="1.5" fill="none" strokeDasharray="4 4" opacity="0.5" />
      )}
      {/* Value area */}
      <polygon points={`${pad},${h - pad} ${toPath(data)} ${pad + ((data.length - 1) / (data.length - 1)) * (w - pad * 2)},${h - pad}`} fill="url(#analGrad)" />
      <polyline points={toPath(data)} stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function AllocationBar({ items }: { items: { label: string; pct: number; color: string }[] }) {
  return (
    <div style={{ height: 8, borderRadius: 999, overflow: 'hidden', display: 'flex', marginBottom: 16 }}>
      {items.map(({ label, pct, color }) => (
        <div key={label} style={{ width: `${pct}%`, background: color, transition: 'width 0.3s' }} />
      ))}
    </div>
  )
}

export default function Analytics() {
  const { id } = useParams()
  const api = useApiClient()

  const { data } = useQuery({
    queryKey: ['portfolio-analytics', id],
    queryFn: async () => {
      const res = await api.get(`/api/portfolio/${id}/analytics`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // /api/portfolio/<id>/analytics returns:
  // {kpis: {total_value, total_cost_basis, total_return, total_return_pct, ...},
  //  allocation: [{symbol, weight_pct, market_value}],
  //  sector: [{name, weight_pct}],
  //  leaderboard: [{symbol, return_pct, return_abs, market_value, weight_pct}],
  //  history: [{date, value}]}
  const kpis = data?.kpis || {}
  const dotColors = ['#60a5fa', '#a78bfa', '#22c55e', '#f59e0b', '#f472b6']

  const analytics = {
    total_value: kpis.total_value ?? 0,
    cost_basis: kpis.total_cost_basis ?? 0,
    total_return: kpis.total_return ?? 0,
    return_pct: kpis.total_return_pct ?? 0,
    day_change: null,
    day_change_pct: null,
    chart: (data?.history || []).map((h: any) => h.value ?? h.close ?? 0).filter((v: number) => v > 0),
    cost_chart: undefined,
    allocation: (data?.allocation || []).map((a: any, i: number) => ({
      symbol: a.symbol,
      pct: typeof a.weight_pct === 'number' ? Number(a.weight_pct.toFixed(1)) : 0,
      value: a.market_value ?? 0,
      color: dotColors[i % dotColors.length],
    })),
    sectors: (data?.sector || []).map((s: any) => ({
      sector: s.name || s.sector,
      pct: typeof s.weight_pct === 'number' ? Number(s.weight_pct.toFixed(1)) : 0,
    })),
    performance: (data?.leaderboard || []).map((p: any) => ({
      symbol: p.symbol,
      pnl_pct: p.return_pct ?? 0,
      pnl: p.return_abs ?? 0,
    })),
  }

  const allocationBarItems = analytics.allocation.map((a: any) => ({ label: a.symbol, pct: a.pct, color: a.color }))

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Link to={`/portfolio/${id}`} style={{ color: '#a8a29e', textDecoration: 'none', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Icon name="arrow_back" size={16} /> Portfolio
            </Link>
          </div>
          <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em' }}>Portfolio Analytics</h1>
        </div>

        {/* KPI STRIP */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 1, background: '#292524', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden', marginBottom: 24 }}>
          {[
            { label: 'Total Value', val: analytics.total_value ? fmt(analytics.total_value) : '-', sub: '', subColor: '#a8a29e' },
            { label: 'Total Return', val: analytics.total_return ? `${analytics.total_return >= 0 ? '+' : ''}${fmt(analytics.total_return)}` : '-', sub: analytics.return_pct != null ? `${analytics.return_pct >= 0 ? '+' : ''}${typeof analytics.return_pct === 'number' ? analytics.return_pct.toFixed(1) : analytics.return_pct}%` : '', subColor: analytics.total_return >= 0 ? '#22c55e' : '#ef4444' },
            { label: 'Holdings', val: String(kpis.holdings_count ?? analytics.allocation.length), sub: 'positions tracked', subColor: '#a8a29e' },
            { label: 'Cost Basis', val: analytics.cost_basis ? fmt(analytics.cost_basis) : '-', sub: 'Total invested', subColor: '#a8a29e' },
          ].map(({ label, val, sub, subColor }) => (
            <div key={label} style={{ background: '#1c1917', padding: '20px 24px' }}>
              <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 8 }}>{label}</div>
              <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 24, fontWeight: 600, letterSpacing: '-0.02em' }}>{val}</div>
              {sub && <div style={{ fontSize: 12, marginTop: 4, color: subColor }}>{sub}</div>}
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* VALUE CHART */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 24px', borderBottom: '1px solid #292524' }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Portfolio Value Over Time</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 11.5, color: '#a8a29e' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 20, height: 2, background: '#22c55e', borderRadius: 1 }} /> Value
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 20, height: 2, background: '#a8a29e', borderRadius: 1, opacity: 0.5 }} /> Cost basis
                  </div>
                </div>
              </div>
              <div style={{ padding: '20px 24px' }}>
                <LineChart data={analytics.chart} costBasis={analytics.cost_chart} gain />
              </div>
            </div>

            {/* ALLOCATION */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 24px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600 }}>Allocation</div>
              <div style={{ padding: '20px 24px' }}>
                <AllocationBar items={allocationBarItems} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {analytics.allocation?.map((a: any) => (
                    <div key={a.symbol} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 10, height: 10, borderRadius: 2, background: a.color, flexShrink: 0 }} />
                      <div style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{a.symbol}</div>
                      <div style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums', color: '#a8a29e' }}>{fmt(a.value)}</div>
                      <div style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums', minWidth: 48, textAlign: 'right' }}>{a.pct}%</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* PERFORMANCE LEADERBOARD */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600 }}>Performance Ranking</div>
              <div>
                {analytics.performance?.map((p: any, i: number) => (
                  <div key={p.symbol} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: i < analytics.performance.length - 1 ? '1px solid rgba(41,37,36,0.5)' : 'none' }}>
                    <div style={{ fontSize: 12, color: '#a8a29e', minWidth: 20 }}>#{i + 1}</div>
                    <Link to={`/ticker/${p.symbol}`} style={{ flex: 1, fontSize: 13, fontWeight: 600, color: '#fafaf9', textDecoration: 'none' }}>{p.symbol}</Link>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: p.pnl_pct >= 0 ? '#22c55e' : '#ef4444', fontVariantNumeric: 'tabular-nums' }}>
                        {p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct}%
                      </div>
                      <div style={{ fontSize: 11.5, color: '#a8a29e', fontVariantNumeric: 'tabular-nums' }}>
                        {p.pnl >= 0 ? '+' : ''}{fmt(p.pnl)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* SECTOR BREAKDOWN */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600 }}>Sector Breakdown</div>
              <div style={{ padding: '16px 20px' }}>
                {analytics.sectors?.map((s: any) => (
                  <div key={s.sector} style={{ marginBottom: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ fontSize: 12.5 }}>{s.sector}</span>
                      <span style={{ fontSize: 12.5, fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}>{s.pct}%</span>
                    </div>
                    <div style={{ height: 6, background: '#232120', borderRadius: 999, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${s.pct}%`, background: '#d6d3d1', opacity: 0.5, borderRadius: 999 }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
