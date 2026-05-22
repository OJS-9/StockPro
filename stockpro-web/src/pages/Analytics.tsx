import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useBreakpoint } from '../hooks/useBreakpoint'
import { useLanguage } from '../LanguageContext'
import { formatCurrency, formatCompact } from '../utils/currency'

function LineChart({ data, dates, costBasis, gain = true, locale = 'en-US' }: { data: number[]; dates?: string[]; costBasis?: number[]; gain?: boolean; locale?: string }) {
  if (!data || data.length < 2) return <div style={{ height: 200, background: '#232120', borderRadius: 8 }} />
  const color = gain ? '#22c55e' : '#ef4444'
  const all = [...data, ...(costBasis || [])]
  const min = Math.min(...all); const max = Math.max(...all)
  const range = max - min || 1
  const w = 600; const h = 200
  const padLeft = 60; const padRight = 12; const padTop = 12; const padBottom = 32

  const toPath = (arr: number[]) => arr.map((v, i) => {
    const x = padLeft + (i / (arr.length - 1)) * (w - padLeft - padRight)
    const y = padTop + (1 - (v - min) / range) * (h - padTop - padBottom)
    return `${x},${y}`
  }).join(' ')

  // Y-axis: 4 ticks
  const yTicks = [0, 1, 2, 3].map(i => {
    const val = min + (range * i) / 3
    const y = padTop + (1 - i / 3) * (h - padTop - padBottom)
    return { val, y }
  })

  // X-axis: ~5 labels from dates
  const xLabels: { label: string; x: number }[] = []
  if (dates && dates.length > 1) {
    const step = Math.max(1, Math.floor((dates.length - 1) / 4))
    for (let i = 0; i < dates.length; i += step) {
      const x = padLeft + (i / (dates.length - 1)) * (w - padLeft - padRight)
      const d = new Date(dates[i])
      xLabels.push({ label: d.toLocaleDateString(locale, { month: 'short', day: 'numeric' }), x })
    }
  }

  return (
    <svg viewBox={`0 0 ${w} ${h}`} fill="none" style={{ width: '100%', height: 200 }}>
      <defs>
        <linearGradient id="analGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Grid lines + Y labels */}
      {yTicks.map(({ val, y }) => (
        <g key={val}>
          <line x1={padLeft} y1={y} x2={w - padRight} y2={y} stroke="#292524" strokeWidth="1" />
          <text x={padLeft - 8} y={y + 4} fill="#78716c" fontSize="10" textAnchor="end" fontFamily="Inter, Heebo, sans-serif">{formatCompact(val)}</text>
        </g>
      ))}
      {/* X labels */}
      {xLabels.map(({ label, x }) => (
        <text key={label + x} x={x} y={h - 6} fill="#78716c" fontSize="10" textAnchor="middle" fontFamily="Inter, Heebo, sans-serif">{label}</text>
      ))}
      {/* Cost basis dashed line */}
      {costBasis && costBasis.length > 1 && (
        <polyline points={toPath(costBasis)} stroke="#a8a29e" strokeWidth="1.5" fill="none" strokeDasharray="4 4" opacity="0.5" />
      )}
      {/* Value area */}
      <polygon points={`${padLeft},${h - padBottom} ${toPath(data)} ${padLeft + ((data.length - 1) / (data.length - 1)) * (w - padLeft - padRight)},${h - padBottom}`} fill="url(#analGrad)" />
      <polyline points={toPath(data)} stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function PieChart({ items }: { items: { label: string; pct: number; color: string }[] }) {
  const size = 180
  const cx = size / 2; const cy = size / 2; const r = 70
  let cumAngle = -90

  const slices = items.filter(i => i.pct > 0).map(item => {
    const angle = (item.pct / 100) * 360
    const startAngle = cumAngle
    cumAngle += angle
    const endAngle = cumAngle
    const startRad = (startAngle * Math.PI) / 180
    const endRad = (endAngle * Math.PI) / 180
    const largeArc = angle > 180 ? 1 : 0
    const x1 = cx + r * Math.cos(startRad)
    const y1 = cy + r * Math.sin(startRad)
    const x2 = cx + r * Math.cos(endRad)
    const y2 = cy + r * Math.sin(endRad)
    const d = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`
    return { ...item, d }
  })

  return (
    <svg viewBox={`0 0 ${size} ${size}`} style={{ width: size, height: size }}>
      {slices.map(s => (
        <path key={s.label} d={s.d} fill={s.color} stroke="#1c1917" strokeWidth="2" />
      ))}
      <circle cx={cx} cy={cy} r={35} fill="#1c1917" />
    </svg>
  )
}

function AllocationBar({ items }: { items: { label: string; pct: number; color: string }[] }) {
  return (
    <div style={{ height: 8, borderRadius: 999, overflow: 'hidden', display: 'flex' }}>
      {items.map(({ label, pct, color }) => (
        <div key={label} style={{ width: `${pct}%`, background: color, transition: 'width 0.3s' }} />
      ))}
    </div>
  )
}

export default function Analytics() {
  const { id } = useParams()
  const api = useApiClient()
  const { isMobile, isTablet } = useBreakpoint()
  const { lang } = useLanguage()
  const locale = lang === 'he' ? 'he-IL' : 'en-US'

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

  const historyRaw = data?.history || []
  const chartDates = historyRaw.map((h: any) => h.date).filter(Boolean)

  const analytics = {
    total_value: kpis.total_value ?? 0,
    cost_basis: kpis.total_cost_basis ?? 0,
    total_return: kpis.total_return ?? 0,
    return_pct: kpis.total_return_pct ?? 0,
    chart: historyRaw.map((h: any) => h.value ?? h.close ?? 0).filter((v: number) => v > 0),
    cost_chart: historyRaw.map((h: any) => h.cost_basis).filter((v: any) => v != null && v > 0),
    // API returns {label, value, pct} for allocation (market breakdown)
    allocation: (data?.allocation || []).map((a: any, i: number) => ({
      symbol: a.label || a.symbol || 'Unknown',
      pct: typeof a.pct === 'number' ? Number(a.pct.toFixed(1)) : (typeof a.weight_pct === 'number' ? Number(a.weight_pct.toFixed(1)) : 0),
      value: a.value ?? a.market_value ?? 0,
      color: dotColors[i % dotColors.length],
    })),
    // API returns {label, pct} for sector breakdown
    sectors: (data?.sector || []).map((s: any) => ({
      sector: s.label || s.name || s.sector,
      pct: typeof s.pct === 'number' ? Number(s.pct.toFixed(1)) : (typeof s.weight_pct === 'number' ? Number(s.weight_pct.toFixed(1)) : 0),
    })),
    performance: (data?.leaderboard || []).map((p: any) => ({
      symbol: p.symbol,
      pnl_pct: typeof p.return_pct === 'number' ? Number(p.return_pct.toFixed(2)) : 0,
      pnl: p.return_abs ?? 0,
    })),
  }

  // Split performance into winners and losers
  const winners = analytics.performance.filter((p: any) => p.pnl_pct >= 0).slice(0, 3)
  const losers = analytics.performance.filter((p: any) => p.pnl_pct < 0).slice(-2)

  const [allocView, setAllocView] = useState<'bar' | 'pie'>('bar')
  const allocationBarItems = analytics.allocation.map((a: any) => ({ label: a.symbol, pct: a.pct, color: a.color }))

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: isMobile ? '20px 16px 60px' : '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Link to={`/portfolio/${id}`} style={{ color: '#a8a29e', textDecoration: 'none', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Icon name="arrow_back" size={16} /> Portfolio
            </Link>
          </div>
          <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em' }}>Portfolio Analytics</h1>
        </div>

        {/* KPI STRIP */}
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : isTablet ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)', gap: 1, background: '#292524', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden', marginBottom: 24 }}>
          {[
            { label: 'Total Value', val: analytics.total_value ? formatCurrency(analytics.total_value) : '-', sub: '', subColor: '#a8a29e' },
            { label: 'Total Return', val: analytics.total_return ? `${analytics.total_return >= 0 ? '+' : ''}${formatCurrency(analytics.total_return)}` : '-', sub: analytics.return_pct != null ? `${analytics.return_pct >= 0 ? '+' : ''}${typeof analytics.return_pct === 'number' ? analytics.return_pct.toFixed(1) : analytics.return_pct}%` : '', subColor: analytics.total_return >= 0 ? '#22c55e' : '#ef4444' },
            { label: 'Holdings', val: String(kpis.holdings_count ?? analytics.allocation.length), sub: 'positions tracked', subColor: '#a8a29e' },
            { label: 'Cost Basis', val: analytics.cost_basis ? formatCurrency(analytics.cost_basis) : '-', sub: 'Total invested', subColor: '#a8a29e' },
          ].map(({ label, val, sub, subColor }) => (
            <div key={label} style={{ background: '#1c1917', padding: '20px 24px' }}>
              <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 8 }}>{label}</div>
              <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 24, fontWeight: 600, letterSpacing: '-0.02em' }}><bdi>{val}</bdi></div>
              {sub && <div style={{ fontSize: 12, marginTop: 4, color: subColor }}>{sub}</div>}
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 340px', gap: 20, alignItems: 'start' }}>
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
                <LineChart data={analytics.chart} dates={chartDates} costBasis={analytics.cost_chart.length > 1 ? analytics.cost_chart : undefined} gain locale={locale} />
              </div>
            </div>

            {/* ALLOCATION */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 24px', borderBottom: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Allocation</div>
                <div style={{ display: 'flex', background: '#232120', borderRadius: 8, padding: 2 }}>
                  <button onClick={() => setAllocView('bar')} style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500, border: 'none', cursor: 'pointer', background: allocView === 'bar' ? '#292524' : 'transparent', color: allocView === 'bar' ? '#fafaf9' : '#a8a29e', transition: 'all 0.15s' }}>
                    <Icon name="bar_chart" size={14} />
                  </button>
                  <button onClick={() => setAllocView('pie')} style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500, border: 'none', cursor: 'pointer', background: allocView === 'pie' ? '#292524' : 'transparent', color: allocView === 'pie' ? '#fafaf9' : '#a8a29e', transition: 'all 0.15s' }}>
                    <Icon name="donut_large" size={14} />
                  </button>
                </div>
              </div>
              <div style={{ padding: '20px 24px' }}>
                {allocView === 'bar' ? (
                  <div style={{ marginBottom: 16 }}>
                    <AllocationBar items={allocationBarItems} />
                  </div>
                ) : (
                  <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
                    <PieChart items={allocationBarItems} />
                  </div>
                )}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {analytics.allocation?.map((a: any) => (
                    <div key={a.symbol} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 10, height: 10, borderRadius: 2, background: a.color, flexShrink: 0 }} />
                      <div style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{a.symbol}</div>
                      <div style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums', color: '#a8a29e' }}>{formatCurrency(a.value)}</div>
                      <div style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums', minWidth: 48, textAlign: 'end' }}>{a.pct}%</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* TOP PERFORMERS */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Icon name="trending_up" size={16} /> Top Performers
              </div>
              <div>
                {winners.length === 0 ? (
                  <div style={{ padding: '16px 20px', fontSize: 12, color: '#a8a29e' }}>No gainers yet</div>
                ) : winners.map((p: any, i: number) => (
                  <div key={p.symbol} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: i < winners.length - 1 ? '1px solid rgba(41,37,36,0.5)' : 'none' }}>
                    <div style={{ fontSize: 12, color: '#a8a29e', minWidth: 20 }}>#{i + 1}</div>
                    <Link to={`/ticker/${p.symbol}`} style={{ flex: 1, fontSize: 13, fontWeight: 600, color: '#fafaf9', textDecoration: 'none' }}>{p.symbol}</Link>
                    <div style={{ textAlign: 'end' }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: '#22c55e', fontVariantNumeric: 'tabular-nums' }}>
                        +{Number(p.pnl_pct).toFixed(2)}%
                      </div>
                      <div style={{ fontSize: 11.5, color: '#a8a29e', fontVariantNumeric: 'tabular-nums' }}>
                        +{formatCurrency(p.pnl)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* WORST PERFORMERS */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Icon name="trending_down" size={16} /> Lagging
              </div>
              <div>
                {losers.length === 0 ? (
                  <div style={{ padding: '16px 20px', fontSize: 12, color: '#a8a29e' }}>No losers</div>
                ) : losers.map((p: any, i: number) => (
                  <div key={p.symbol} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: i < losers.length - 1 ? '1px solid rgba(41,37,36,0.5)' : 'none' }}>
                    <div style={{ fontSize: 12, color: '#a8a29e', minWidth: 20 }}>#{i + 1}</div>
                    <Link to={`/ticker/${p.symbol}`} style={{ flex: 1, fontSize: 13, fontWeight: 600, color: '#fafaf9', textDecoration: 'none' }}>{p.symbol}</Link>
                    <div style={{ textAlign: 'end' }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: '#ef4444', fontVariantNumeric: 'tabular-nums' }}>
                        {Number(p.pnl_pct).toFixed(2)}%
                      </div>
                      <div style={{ fontSize: 11.5, color: '#a8a29e', fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrency(p.pnl)}
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
