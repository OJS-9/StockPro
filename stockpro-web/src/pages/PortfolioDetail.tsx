import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import Skeleton from '../components/Skeleton'
import { useApiClient } from '../api/client'
import { useLanguage } from '../LanguageContext'
import { useBreakpoint } from '../hooks/useBreakpoint'

const fmtCompact = (n: number) => {
  if (n >= 1000000) return `$${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}K`
  return `$${n.toFixed(0)}`
}

const RANGES = ['1W', '1M', '3M', 'YTD', '1Y']

function LineChart({ data, dates, gain = true, loading = false, locale = 'en-US' }: { data: number[]; dates?: string[]; gain?: boolean; loading?: boolean; locale?: string }) {
  if (loading) return (
    <div style={{ height: 160, background: '#232120', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ fontSize: 12, color: '#a8a29e' }}>Loading chart...</div>
    </div>
  )
  if (!data || data.length < 2) return (
    <div style={{ height: 160, background: '#232120', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ fontSize: 12, color: '#a8a29e' }}>No chart data for this range</div>
    </div>
  )
  const color = gain ? '#22c55e' : '#ef4444'
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const w = 600
  const h = 160
  const padLeft = 60; const padRight = 12; const padTop = 8; const padBottom = 28

  const pts = data.map((v, i) => {
    const x = padLeft + (i / (data.length - 1)) * (w - padLeft - padRight)
    const y = padTop + (1 - (v - min) / range) * (h - padTop - padBottom)
    return `${x},${y}`
  }).join(' ')
  const lastX = padLeft + ((data.length - 1) / (data.length - 1)) * (w - padLeft - padRight)

  // Y-axis: 4 ticks
  const yTicks = [0, 1, 2, 3].map(i => {
    const val = min + (range * i) / 3
    const y = padTop + (1 - i / 3) * (h - padTop - padBottom)
    return { val, y }
  })

  // X-axis: ~5 labels
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
    <svg viewBox={`0 0 ${w} ${h}`} fill="none" style={{ width: '100%', height: 160 }}>
      <defs>
        <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Grid lines + Y labels */}
      {yTicks.map(({ val, y }) => (
        <g key={val}>
          <line x1={padLeft} y1={y} x2={w - padRight} y2={y} stroke="#292524" strokeWidth="1" />
          <text x={padLeft - 8} y={y + 4} fill="#78716c" fontSize="10" textAnchor="end" fontFamily="Inter, sans-serif">{fmtCompact(val)}</text>
        </g>
      ))}
      {/* X labels */}
      {xLabels.map(({ label, x }) => (
        <text key={label + x} x={x} y={h - 4} fill="#78716c" fontSize="10" textAnchor="middle" fontFamily="Inter, sans-serif">{label}</text>
      ))}
      <polygon points={`${padLeft},${h - padBottom} ${pts} ${lastX},${h - padBottom}`} fill="url(#chartGrad)" />
      <polyline points={pts} stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export default function PortfolioDetail() {
  const { id } = useParams()
  const [range, setRange] = useState('1M')
  const api = useApiClient()
  const { t } = useTranslation()
  const { lang } = useLanguage()
  const { isMobile } = useBreakpoint()

  const locale = lang === 'he' ? 'he-IL' : 'en-US'
  const fmt = (n: number) => new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' }).format(n)

  // /api/portfolio/<id>/history returns {history: [{date, value}], granularity}
  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['portfolio-history', id, range],
    queryFn: async () => {
      const res = await api.get(`/api/portfolio/${id}/history?range=${range}`)
      if (!res.ok) return { history: [], granularity: 'daily' }
      return res.json()
    },
  })

  // /api/portfolio/<id>/prices returns {holdings, total_market_value, total_unrealized_gain, total_unrealized_gain_pct}
  const { data: pricesData } = useQuery({
    queryKey: ['portfolio-prices', id],
    queryFn: async () => {
      const res = await api.get(`/api/portfolio/${id}/prices`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // /portfolio/<id>?format=json returns {portfolio, summary, holdings}
  const { data: portfolioData, isLoading: portfolioLoading } = useQuery({
    queryKey: ['portfolio-detail', id],
    queryFn: async () => {
      const res = await api.get(`/api/portfolio/${id}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const { data: txData } = useQuery({
    queryKey: ['portfolio-transactions', id],
    queryFn: async () => {
      const res = await api.get(`/api/portfolio/${id}/transactions?limit=5`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // Merge holdings: prefer prices data (has live prices), fall back to portfolio summary
  const holdingsRaw = pricesData?.holdings || portfolioData?.holdings || []
  const holdings = holdingsRaw.map((h: any) => ({
    symbol: h.symbol,
    name: h.name || h.symbol,
    shares: h.total_quantity ?? h.quantity ?? h.shares ?? 0,
    avg_cost: h.average_cost ?? h.avg_cost ?? 0,
    current_price: h.current_price ?? null,
    market_value: h.market_value ?? 0,
    pnl: h.unrealized_gain ?? h.pnl ?? 0,
    pnl_pct: h.unrealized_gain_pct ?? h.pnl_pct ?? 0,
  }))

  const transactions = txData?.transactions || []
  const portfolioName = portfolioData?.portfolio?.name || 'Portfolio'
  const totalValue = pricesData?.total_market_value ?? 0
  const pnl = pricesData?.total_unrealized_gain ?? 0
  const pnlPct = pricesData?.total_unrealized_gain_pct ?? 0
  // Chart data: history returns [{date, value}] — extract value and date arrays
  const historyRaw = historyData?.history || []
  const chartData: number[] = historyRaw.map((h: any) => h.value ?? h.close ?? 0).filter((v: number) => v > 0)
  const chartDates: string[] = historyRaw.map((h: any) => h.date).filter(Boolean)

  const dotColors = ['#60a5fa', '#a78bfa', '#22c55e', '#f59e0b', '#f472b6']

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1200, margin: '0 auto', padding: isMobile ? '20px 16px 60px' : '36px 48px 80px' }}>

        {portfolioLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <Skeleton height={32} width={200} />
            <Skeleton height={200} />
            <Skeleton height={300} />
          </div>
        )}

        {!portfolioLoading && <>
        {/* HEADER */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Link to="/portfolio" style={{ color: '#a8a29e', textDecoration: 'none', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
                <Icon name="arrow_back" size={16} /> {t('portfolioDetail.portfolios')}
              </Link>
              <Icon name="chevron_right" size={16} />
              <span style={{ fontSize: 13, color: '#fafaf9' }}>{portfolioName}</span>
            </div>
            <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>{portfolioName}</h1>
            <div style={{ fontSize: 13, color: '#a8a29e' }}>{holdings.length} {t('portfolioDetail.holdings')}</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Link to={`/portfolio/${id}/add`} style={{ background: 'transparent', border: '1px solid #292524', color: '#a8a29e', fontSize: 13, fontWeight: 500, padding: '8px 16px', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
              <Icon name="add" size={16} /> {t('portfolioDetail.addTransaction')}
            </Link>
            <Link to={`/portfolio/${id}/import`} style={{ background: 'transparent', border: '1px solid #292524', color: '#a8a29e', fontSize: 13, fontWeight: 500, padding: '8px 16px', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
              <Icon name="upload" size={16} /> {t('portfolioDetail.importCsv')}
            </Link>
            <Link to={`/portfolio/${id}/analytics`} style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
              <Icon name="analytics" size={16} /> {t('portfolioDetail.analytics')}
            </Link>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 320px', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* CHART CARD */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '20px 24px', borderBottom: '1px solid #292524' }}>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 4 }}>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 6 }}>{t('portfolioDetail.portfolioValue')}</div>
                    <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: isMobile ? 26 : 36, fontWeight: 600, letterSpacing: '-0.03em' }}>{fmt(totalValue)}</div>
                  </div>
                  <div style={{ textAlign: 'end' }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                      {pnl >= 0 ? '+' : ''}{fmt(pnl)}
                    </div>
                    <div style={{ fontSize: 13, color: pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                      {pnl >= 0 ? '+' : ''}{Number(pnlPct).toFixed(2)}% all time
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 4, marginTop: 16 }}>
                  {RANGES.map(r => (
                    <button
                      key={r}
                      onClick={() => setRange(r)}
                      style={{ padding: '5px 12px', borderRadius: 7, fontSize: 12, fontWeight: 500, border: 'none', cursor: 'pointer', background: range === r ? 'rgba(214,211,209,0.12)' : 'transparent', color: range === r ? '#fafaf9' : '#a8a29e', transition: 'all 0.15s' }}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ padding: '20px 24px' }}>
                <LineChart data={chartData} dates={chartDates} gain={pnl >= 0} loading={historyLoading} locale={locale} />
              </div>
            </div>

            {/* HOLDINGS TABLE */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 24px', borderBottom: '1px solid #292524' }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{t('portfolioDetail.holdings')}</div>
                <Link to={`/portfolio/${id}/add`} style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Icon name="add" size={14} /> {t('portfolioDetail.add')}
                </Link>
              </div>
              <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: isMobile ? 640 : undefined }}>
                <thead>
                  <tr style={{ padding: '0 24px' }}>
                    {['Holding', 'Shares', 'Avg Cost', t('portfolioDetail.currentPrice'), 'Market Value', 'P&L', 'Return'].map(h => (
                      <th key={h} style={{ fontSize: 10.5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', textAlign: h === 'Holding' ? 'start' : 'end', padding: '12px 24px', borderBottom: '1px solid #292524' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h: any, i: number) => (
                    <tr key={h.symbol}>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', fontSize: 13.5 }}>
                        <Link to={`/portfolio/${id}/holding/${h.symbol}`} style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: dotColors[i % dotColors.length], flexShrink: 0 }} />
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9' }}>{h.symbol}</div>
                            <div style={{ fontSize: 11.5, color: '#a8a29e' }}>{h.name}</div>
                          </div>
                        </Link>
                      </td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{Number(h.shares).toFixed(2)}</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{fmt(h.avg_cost)}</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{h.current_price != null ? fmt(h.current_price) : <span style={{ color: '#57534e' }}>--</span>}</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{fmt(h.market_value)}</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: h.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                        {h.pnl >= 0 ? '+' : ''}{fmt(h.pnl)}
                      </td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end' }}>
                        <span style={{ display: 'inline-flex', fontSize: 12, fontWeight: 500, padding: '3px 8px', borderRadius: 999, background: h.pnl_pct >= 0 ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)', color: h.pnl_pct >= 0 ? '#22c55e' : '#ef4444', border: `1px solid ${h.pnl_pct >= 0 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}` }}>
                          {h.pnl_pct >= 0 ? '+' : ''}{Number(h.pnl_pct).toFixed(2)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          </div>

          {/* SIDEBAR */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600 }}>{t('portfolioDetail.recentTransactions')}</div>
              <div style={{ padding: '8px 0' }}>
                {transactions.length === 0 ? (
                  <div style={{ padding: '16px 20px', fontSize: 12, color: '#a8a29e' }}>{t('portfolioDetail.noTransactions')}</div>
                ) : transactions.map((t: any) => {
                  // API fields: transaction_id, symbol, transaction_type, quantity, price_per_unit, transaction_date
                  const txType = (t.transaction_type || t.type || 'BUY').toUpperCase()
                  const isBuy = txType === 'BUY'
                  const dateStr = t.transaction_date ? new Date(t.transaction_date).toLocaleDateString(locale, { month: 'short', day: 'numeric' }) : (t.date || '')
                  return (
                  <div key={t.transaction_id || t.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)' }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: isBuy ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', border: `1px solid ${isBuy ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Icon name={isBuy ? 'add' : 'remove'} size={16} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{txType} {t.symbol}</div>
                      <div style={{ fontSize: 11.5, color: '#a8a29e' }}>{t.quantity ?? t.shares} shares @ {fmt(t.price_per_unit ?? t.price ?? 0)}</div>
                    </div>
                    <div style={{ fontSize: 11, color: '#a8a29e' }}>{dateStr}</div>
                  </div>
                  )
                })}
                <div style={{ padding: '12px 20px' }}>
                  <Link to={`/portfolio/${id}/add`} style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Icon name="add" size={14} /> {t('portfolioDetail.addTransactionLink')}
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
        </>}
      </main>
    </div>
  )
}
