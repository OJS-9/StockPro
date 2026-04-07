import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
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
  const [range, setRange] = useState('1M')

  const { data: hist } = useQuery({
    queryKey: ['ticker-history', symbol, range],
    queryFn: async () => {
      const res = await api.get(`/api/ticker/${symbol}/history?range=${range}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const { data: fundData } = useQuery({
    queryKey: ['ticker-fundamentals', symbol],
    queryFn: async () => {
      const res = await api.get(`/api/ticker/${symbol}/fundamentals`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const { data: newsData } = useQuery({
    queryKey: ['ticker-news', symbol],
    queryFn: async () => {
      const res = await api.get(`/api/news?symbol=${symbol}`)
      if (!res.ok) throw new Error('Failed')
      // /api/news returns a list directly, not {news: [...]}
      const d = await res.json()
      return Array.isArray(d) ? d : (d.news || d.articles || [])
    },
  })

  const { data: posData } = useQuery({
    queryKey: ['position', symbol],
    queryFn: async () => {
      const res = await api.get(`/api/position_check/${symbol}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // /api/ticker/<symbol>/history returns {history: [{date, close}]}
  // /api/ticker/<symbol>/fundamentals returns {symbol, name, sector, market_cap, pe_ratio, eps, revenue, gross_margin, week_52_high, week_52_low, beta, current_price, ...}
  const historyArr: {date: string; close: number}[] = hist?.history || []
  const chartData: number[] = historyArr.map((h: any) => h.close ?? 0).filter((v: number) => v > 0)
  const lastClose = chartData.length > 0 ? chartData[chartData.length - 1] : 0
  const prevClose = chartData.length > 1 ? chartData[chartData.length - 2] : lastClose
  const price = fundData?.current_price ?? lastClose
  const changePct = price && prevClose ? Number((((price - prevClose) / prevClose) * 100).toFixed(2)) : 0
  const gain = changePct >= 0

  const fundamentals = fundData || {}

  // newsData is already the array (normalized in queryFn)
  const news = Array.isArray(newsData) ? newsData : []
  const position = posData?.position || null

  const fundamentalItems = [
    { label: 'Market Cap', val: fundamentals.market_cap ? fmtCompact(fundamentals.market_cap) : '-' },
    { label: 'P/E Ratio', val: fundamentals.pe_ratio != null ? Number(fundamentals.pe_ratio).toFixed(1) : '-' },
    { label: 'Revenue', val: fundamentals.revenue ? fmtCompact(fundamentals.revenue) : '-' },
    { label: 'Gross Margin', val: fundamentals.gross_margin != null ? `${(fundamentals.gross_margin * 100).toFixed(1)}%` : '-' },
    { label: 'EPS', val: fundamentals.eps != null ? `$${Number(fundamentals.eps).toFixed(2)}` : '-' },
    { label: 'Beta', val: fundamentals.beta != null ? Number(fundamentals.beta).toFixed(2) : '-' },
    { label: '52W High', val: fundamentals.week_52_high ? fmt(fundamentals.week_52_high) : '-' },
    { label: '52W Low', val: fundamentals.week_52_low ? fmt(fundamentals.week_52_low) : '-' },
  ]

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1200, margin: '0 auto', padding: '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <div style={{ width: 48, height: 48, borderRadius: 12, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Nunito, sans-serif', fontSize: 14, fontWeight: 700, color: '#d6d3d1' }}>
                {(symbol || '').slice(0, 2)}
              </div>
              <div>
                <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em' }}>{symbol}</h1>
                <div style={{ fontSize: 13, color: '#a8a29e' }}>NASDAQ &nbsp;&middot;&nbsp; Technology</div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{ fontFamily: 'Nunito, sans-serif', fontSize: 36, fontWeight: 600, letterSpacing: '-0.03em' }}>{fmt(price)}</span>
              <span style={{ fontSize: 16, fontWeight: 500, color: gain ? '#22c55e' : '#ef4444' }}>
                {gain ? '+' : ''}{changePct}% today
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Link to={`/research?ticker=${symbol}`} style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
              <Icon name="auto_awesome" size={16} /> Research
            </Link>
            <button style={{ background: 'transparent', border: '1px solid #292524', color: '#a8a29e', fontSize: 13, fontWeight: 500, padding: '8px 16px', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="notifications_none" size={16} /> Set Alert
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* CHART */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', display: 'flex', gap: 4 }}>
                {RANGES.map(r => (
                  <button key={r} onClick={() => setRange(r)} style={{ padding: '5px 12px', borderRadius: 7, fontSize: 12, fontWeight: 500, border: 'none', cursor: 'pointer', background: range === r ? 'rgba(214,211,209,0.12)' : 'transparent', color: range === r ? '#fafaf9' : '#a8a29e' }}>
                    {r}
                  </button>
                ))}
              </div>
              <div style={{ padding: '20px 20px' }}>
                <PriceChart data={chartData} gain={gain} />
              </div>
            </div>

            {/* FUNDAMENTALS */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600 }}>Fundamentals</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 0 }}>
                {fundamentalItems.map(({ label, val }, i) => (
                  <div key={label} style={{ padding: '16px 20px', borderRight: i % 5 < 4 ? '1px solid #292524' : 'none', borderBottom: i < 5 ? '1px solid #292524' : 'none' }}>
                    <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 6 }}>{label}</div>
                    <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 18, fontWeight: 600, letterSpacing: '-0.02em' }}>{val}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* NEWS */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600 }}>Recent News</div>
              <div style={{ padding: '8px 0' }}>
                {news.map((n: any, i: number) => (
                  <div key={i} style={{ padding: '14px 20px', borderBottom: i < news.length - 1 ? '1px solid rgba(41,37,36,0.5)' : 'none', cursor: 'pointer' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <span style={{ fontSize: 11.5, fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: n.sentiment === 'bull' ? 'rgba(34,197,94,0.08)' : n.sentiment === 'bear' ? 'rgba(239,68,68,0.08)' : '#232120', color: n.sentiment === 'bull' ? '#22c55e' : n.sentiment === 'bear' ? '#ef4444' : '#a8a29e', border: `1px solid ${n.sentiment === 'bull' ? 'rgba(34,197,94,0.2)' : n.sentiment === 'bear' ? 'rgba(239,68,68,0.2)' : '#292524'}` }}>
                        {n.sentiment === 'bull' ? 'Bullish' : n.sentiment === 'bear' ? 'Bearish' : 'Neutral'}
                      </span>
                      <span style={{ fontSize: 11, color: '#a8a29e' }}>{n.source}</span>
                      <span style={{ fontSize: 11, color: '#a8a29e' }}>&middot;</span>
                      <span style={{ fontSize: 11, color: '#a8a29e' }}>{n.time}</span>
                    </div>
                    <div style={{ fontSize: 14, lineHeight: 1.5, color: 'rgba(250,250,249,0.85)' }}>{n.title}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* SIDEBAR */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Position card */}
            {position && (
              <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Icon name="pie_chart" size={16} /> Your Position
                </div>
                <div style={{ padding: 20 }}>
                  <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 24, fontWeight: 600, marginBottom: 4 }}>{fmt(position.market_value)}</div>
                  <div style={{ fontSize: 12, color: '#a8a29e', marginBottom: 16 }}>{position.shares} shares @ {fmt(position.avg_cost)} avg</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderTop: '1px solid #292524' }}>
                    <span style={{ fontSize: 12, color: '#a8a29e' }}>Unrealized P&L</span>
                    <span style={{ fontSize: 13, fontWeight: 500, color: position.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                      {position.pnl >= 0 ? '+' : ''}{fmt(position.pnl)} ({position.pnl_pct >= 0 ? '+' : ''}{position.pnl_pct}%)
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Research CTA */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>AI Research</div>
              <p style={{ fontSize: 13, color: '#a8a29e', lineHeight: 1.6, marginBottom: 16 }}>
                Get a deep AI research report on {symbol} — fundamentals, technicals, risk analysis, and more.
              </p>
              <Link to={`/research?ticker=${symbol}`} style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%', background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '10px 16px', borderRadius: 8, textDecoration: 'none', justifyContent: 'center' }}>
                <Icon name="auto_awesome" size={16} /> Research {symbol}
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
