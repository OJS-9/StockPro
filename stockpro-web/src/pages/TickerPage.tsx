import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import Skeleton from '../components/Skeleton'
import { useApiClient } from '../api/client'

const fmt = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
const fmtCompact = (n: number) => new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n)

const RANGES = ['1D', '1W', '1M', '3M', '1Y']

function PriceChart({ data, gain = true }: { data: number[]; gain?: boolean }) {
  if (!data || data.length < 2) return <div style={{ height: 160, background: '#232120', borderRadius: 8 }} />
  const color = gain ? '#22c55e' : '#ef4444'
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const w = 600; const h = 160; const pad = 8
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x},${y}`
  }).join(' ')
  const lastX = pad + ((data.length - 1) / (data.length - 1)) * (w - pad * 2)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" fill="none" style={{ width: '100%', height: 160 }}>
      <defs>
        <linearGradient id="tickerGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`${pad},${h - pad} ${pts} ${lastX},${h - pad}`} fill="url(#tickerGrad)" />
      <polyline points={pts} stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export default function TickerPage() {
  const { symbol } = useParams()
  const api = useApiClient()
  const [range, setRange] = useState('3M')

  const { data: hist } = useQuery({
    queryKey: ['ticker-history', symbol, range],
    queryFn: async () => {
      const res = await api.get(`/api/ticker/${symbol}/history?range=${range}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const { data: fundData, isLoading: fundLoading } = useQuery({
    queryKey: ['ticker-fundamentals', symbol],
    queryFn: async () => {
      const res = await api.get(`/api/ticker/${symbol}/fundamentals`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const { data: posData } = useQuery({
    queryKey: ['position', symbol],
    queryFn: async () => {
      const res = await api.get(`/api/position_check/${symbol}`)
      if (!res.ok) return { position: null }
      return res.json()
    },
  })

  const { data: reportsData } = useQuery({
    queryKey: ['ticker-reports', symbol],
    queryFn: async () => {
      const res = await api.get(`/api/reports?ticker=${symbol}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const historyArr: { date: string; close: number }[] = hist?.history || []
  const chartData: number[] = historyArr.map((h: any) => h.close ?? 0).filter((v: number) => v > 0)
  const lastClose = chartData.length > 0 ? chartData[chartData.length - 1] : 0
  const prevClose = chartData.length > 1 ? chartData[chartData.length - 2] : lastClose
  const price = fundData?.current_price ?? lastClose
  const changeAbs = price && prevClose ? price - prevClose : 0
  const changePct = price && prevClose ? Number((((price - prevClose) / prevClose) * 100).toFixed(2)) : 0
  const gain = changePct >= 0

  const fundamentals = fundData || {}
  const position = posData?.position || null
  const tickerReports: any[] = reportsData?.reports || []

  const name = fundamentals.name || symbol
  const sector = fundamentals.sector || ''
  const industry = fundamentals.industry || ''

  const statItems = [
    { label: 'Market Cap', val: fundamentals.market_cap ? fmtCompact(fundamentals.market_cap) : '-' },
    { label: 'P/E Ratio', val: fundamentals.pe_ratio != null ? `${Number(fundamentals.pe_ratio).toFixed(1)}x` : '-' },
    { label: 'EPS (TTM)', val: fundamentals.eps != null ? `$${Number(fundamentals.eps).toFixed(2)}` : '-' },
    { label: 'Revenue (TTM)', val: fundamentals.revenue ? fmtCompact(fundamentals.revenue) : '-' },
    { label: 'Gross Margin', val: fundamentals.gross_margin != null ? `${(fundamentals.gross_margin * 100).toFixed(1)}%` : '-', highlight: fundamentals.gross_margin != null && fundamentals.gross_margin > 0.4 },
    { label: '52W Range', val: fundamentals.week_52_high && fundamentals.week_52_low ? `$${Number(fundamentals.week_52_low).toFixed(0)} – $${Number(fundamentals.week_52_high).toFixed(0)}` : '-', small: true },
    { label: 'Avg Volume', val: fundamentals.avg_volume ? fmtCompact(fundamentals.avg_volume) : '-' },
    { label: 'Beta', val: fundamentals.beta != null ? Number(fundamentals.beta).toFixed(2) : '-' },
    { label: 'Dividend', val: fundamentals.dividend_yield != null ? `${(fundamentals.dividend_yield * 100).toFixed(2)}%` : '-', muted: !fundamentals.dividend_yield },
  ]

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '36px 48px 80px' }}>

        {fundLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <Skeleton height={40} width={120} />
              <Skeleton height={20} width={200} />
            </div>
            <Skeleton height={50} width={180} />
            <Skeleton height={160} borderRadius={14} />
            <Skeleton height={200} borderRadius={14} />
          </div>
        )}

        {!fundLoading && <>
        {/* TICKER HEADER */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <span style={{ fontFamily: 'Nunito, sans-serif', fontSize: 36, fontWeight: 700, letterSpacing: '-0.03em' }}>{symbol}</span>
              <div>
                <div style={{ fontSize: 15, color: '#a8a29e' }}>{name !== symbol ? name : ''}</div>
                <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                  {sector && (
                    <span style={{ fontSize: 12, fontWeight: 500, padding: '4px 10px', borderRadius: 999, border: '1px solid #292524', color: '#a8a29e', background: '#1c1917' }}>
                      {sector}
                    </span>
                  )}
                  {industry && industry !== sector && (
                    <span style={{ fontSize: 12, fontWeight: 500, padding: '4px 10px', borderRadius: 999, border: '1px solid #292524', color: '#a8a29e', background: '#1c1917' }}>
                      {industry}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14 }}>
              <span style={{ fontFamily: 'Nunito, sans-serif', fontSize: 44, fontWeight: 600, letterSpacing: '-0.04em', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
                {price ? fmt(price) : '-'}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingBottom: 6 }}>
                <span style={{ fontSize: 18, fontWeight: 600, color: gain ? '#22c55e' : '#ef4444', fontVariantNumeric: 'tabular-nums' }}>
                  {gain ? '+' : ''}{fmt(changeAbs)}
                </span>
                <span style={{ fontSize: 15, fontWeight: 500, color: gain ? '#22c55e' : '#ef4444', fontVariantNumeric: 'tabular-nums' }}>
                  ({gain ? '+' : ''}{changePct}%)
                </span>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, paddingTop: 8 }}>
            <button style={{ background: 'transparent', color: '#a8a29e', fontSize: 13, fontWeight: 500, padding: '9px 16px', borderRadius: 8, border: '1px solid #292524', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="visibility" size={16} /> Watch
            </button>
            <button style={{ background: 'transparent', color: '#a8a29e', fontSize: 13, fontWeight: 500, padding: '9px 16px', borderRadius: 8, border: '1px solid #292524', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="add_alert" size={16} /> Set Alert
            </button>
            <Link
              to={`/research?ticker=${symbol}`}
              style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 14, fontWeight: 700, padding: '10px 22px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', fontFamily: 'Nunito, sans-serif' }}
            >
              <Icon name="auto_awesome" size={18} /> Research {symbol}
            </Link>
          </div>
        </div>

        {/* PRICE CHART */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: '20px 20px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <div style={{ fontSize: 13, color: '#a8a29e' }}>Price (USD)</div>
              <div style={{ display: 'flex', gap: 2 }}>
                {RANGES.map(r => (
                  <button
                    key={r}
                    onClick={() => setRange(r)}
                    style={{ fontSize: 12, fontWeight: 500, padding: '5px 10px', borderRadius: 6, border: 'none', background: range === r ? 'rgba(214,211,209,0.1)' : 'transparent', color: range === r ? '#fafaf9' : '#a8a29e', cursor: 'pointer', transition: 'all 0.15s' }}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
            <PriceChart data={chartData} gain={gain} />
          </div>
        </div>

        {/* MAIN LAYOUT */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* KEY STATISTICS */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid #292524', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600 }}>
                <Icon name="bar_chart" size={16} style={{ color: '#a8a29e' }} />
                Key Statistics
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0, background: '#292524' }}>
                {statItems.map(({ label, val, highlight, small, muted }) => (
                  <div key={label} style={{ background: '#1c1917', padding: '14px 18px' }}>
                    <div style={{ fontSize: 10.5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#a8a29e', marginBottom: 4 }}>{label}</div>
                    <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: small ? 13 : 16, fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: highlight ? '#22c55e' : muted ? '#a8a29e' : '#fafaf9' }}>
                      {val}
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* RIGHT PANEL */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* AI REPORTS */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600 }}>
                  <Icon name="description" size={16} style={{ color: '#a8a29e' }} />
                  AI Reports
                </div>
                <Link to={`/research?ticker=${symbol}`} style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                  New <Icon name="add" size={14} />
                </Link>
              </div>
              {tickerReports.length === 0 ? (
                <div style={{ padding: '20px', textAlign: 'center', color: '#a8a29e', fontSize: 13 }}>
                  No reports for {symbol} yet
                </div>
              ) : (
                tickerReports.slice(0, 4).map((r: any) => {
                  const rid = r.report_id || r.id
                  const title = r.title || `${symbol} Research Report`
                  const date = r.created_at ? new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''
                  const type = r.trade_type || r.type || ''
                  return (
                    <Link
                      key={rid}
                      to={`/report/${rid}`}
                      style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '13px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)', textDecoration: 'none', transition: 'background 0.15s' }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <div style={{ width: 34, height: 34, borderRadius: 9, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <Icon name="query_stats" size={17} style={{ color: '#a8a29e' }} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</div>
                        <div style={{ fontSize: 11.5, color: '#a8a29e' }}>
                          {type && <span>{type} &middot; </span>}
                          {date}
                        </div>
                      </div>
                    </Link>
                  )
                })
              )}
            </div>

            {/* YOUR POSITION (if holding) */}
            {position && (
              <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
                <div style={{ padding: '14px 20px', borderBottom: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600 }}>
                    <Icon name="pie_chart" size={16} style={{ color: '#a8a29e' }} />
                    Your Position
                  </div>
                </div>
                <div style={{ padding: '16px 20px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                    <div>
                      <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#a8a29e', marginBottom: 4 }}>Shares held</div>
                      <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 20, fontWeight: 600 }}>{position.shares}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#a8a29e', marginBottom: 4 }}>Mkt Value</div>
                      <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 20, fontWeight: 600 }}>{fmt(position.market_value)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#a8a29e', marginBottom: 4 }}>Avg Cost</div>
                      <div style={{ fontSize: 15, fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}>{fmt(position.avg_cost)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#a8a29e', marginBottom: 4 }}>Total Return</div>
                      <div style={{ fontSize: 15, fontWeight: 500, fontVariantNumeric: 'tabular-nums', color: position.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                        {position.pnl >= 0 ? '+' : ''}{fmt(position.pnl)} ({position.pnl_pct >= 0 ? '+' : ''}{position.pnl_pct}%)
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>
        </>}
      </main>
    </div>
  )
}
