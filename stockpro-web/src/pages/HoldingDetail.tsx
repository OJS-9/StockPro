import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useBreakpoint } from '../hooks/useBreakpoint'
import { useLanguage } from '../LanguageContext'
import { formatCurrency } from '../utils/currency'

function LineChart({ data, gain = true }: { data: number[]; gain?: boolean }) {
  if (!data || data.length < 2) return <div style={{ height: 140, background: '#232120', borderRadius: 8 }} />
  const color = gain ? '#22c55e' : '#ef4444'
  const min = Math.min(...data); const max = Math.max(...data)
  const range = max - min || 1
  const w = 600; const h = 140; const pad = 8
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x},${y}`
  }).join(' ')
  const lastX = pad + ((data.length - 1) / (data.length - 1)) * (w - pad * 2)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" fill="none" style={{ width: '100%', height: 140 }}>
      <defs>
        <linearGradient id="holdingGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.2" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`${pad},${h - pad} ${pts} ${lastX},${h - pad}`} fill="url(#holdingGrad)" />
      <polyline points={pts} stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export default function HoldingDetail() {
  const { id, symbol } = useParams()
  const api = useApiClient()
  const queryClient = useQueryClient()
  const { isMobile } = useBreakpoint()
  const { t } = useTranslation()
  const { lang } = useLanguage()
  const locale = lang === 'he' ? 'he-IL' : 'en-US'

  // /portfolio/<id>/holding/<symbol>?format=json returns {portfolio, holding, transactions}
  const { data: holdData } = useQuery({
    queryKey: ['holding', id, symbol],
    queryFn: async () => {
      const res = await api.get(`/api/portfolio/${id}/holding/${symbol}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // /api/ticker/<symbol>/history returns {history: [{date, close}]}
  const { data: priceHist } = useQuery({
    queryKey: ['ticker-history', symbol, '3M'],
    queryFn: async () => {
      const res = await api.get(`/api/ticker/${symbol}/history?range=3M`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // Normalize holding from API response
  const rawHolding = holdData?.holding
  const holding = rawHolding ? {
    symbol: rawHolding.symbol || symbol,
    name: rawHolding.name || `${symbol}`,
    shares: rawHolding.total_quantity ?? rawHolding.shares ?? 0,
    avg_cost: rawHolding.average_cost ?? rawHolding.avg_cost ?? 0,
    current_price: rawHolding.current_price != null ? Number(rawHolding.current_price) : 0,
    market_value: rawHolding.market_value != null ? Number(rawHolding.market_value) : 0,
    pnl: rawHolding.unrealized_gain != null ? Number(rawHolding.unrealized_gain) : 0,
    pnl_pct: rawHolding.unrealized_gain_pct != null ? Number(rawHolding.unrealized_gain_pct) : 0,
    currency: rawHolding.currency || 'USD',
  } : {
    symbol: symbol || '', name: symbol || '', shares: 0, avg_cost: 0, current_price: 0, market_value: 0, pnl: 0, pnl_pct: 0, currency: 'USD',
  }

  // Normalize transactions from API response
  const rawTransactions = holdData?.transactions || []
  const transactions = rawTransactions.map((t: any) => ({
    id: t.transaction_id || t.id,
    type: (t.transaction_type || t.type || 'BUY').toUpperCase(),
    shares: t.quantity ?? t.shares ?? 0,
    price: t.price_per_unit ?? t.price ?? 0,
    date: t.transaction_date ? new Date(t.transaction_date).toLocaleDateString(locale, { month: 'short', day: 'numeric', year: 'numeric' }) : (t.date || ''),
    total: (t.quantity ?? t.shares ?? 0) * (t.price_per_unit ?? t.price ?? 0),
  }))

  // History chart data: [{date, close}]
  const chartData: number[] = (priceHist?.history || []).map((h: any) => h.close ?? h.value ?? 0).filter((v: number) => v > 0)
  const gain = holding.pnl >= 0

  const deleteMutation = useMutation({
    mutationFn: async (txId: string) => {
      const res = await api.delete(`/api/portfolio/${id}/transaction/${txId}`)
      if (!res.ok) throw new Error('Failed to delete transaction')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['holding', id, symbol] })
      toast.success(t('transactions.toasts.deleted'))
    },
    onError: (e: any) => toast.error(e.message || t('transactions.toasts.deleteFailed')),
  })

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: isMobile ? '20px 16px 60px' : '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Link to={`/portfolio/${id}`} style={{ color: '#a8a29e', textDecoration: 'none', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Icon name="arrow_back" size={16} /> Portfolio
            </Link>
            <Icon name="chevron_right" size={16} />
            <span style={{ fontSize: 13, color: '#fafaf9' }}>{symbol}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
              <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>{symbol}</h1>
              <div style={{ fontSize: 13, color: '#a8a29e' }}>{holding.name} &nbsp;&middot;&nbsp; {holding.shares} shares</div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Link to={`/portfolio/${id}/add`} style={{ background: 'transparent', border: '1px solid #292524', color: '#a8a29e', fontSize: 13, fontWeight: 500, padding: '8px 16px', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
                <Icon name="add" size={16} /> Add More
              </Link>
              <Link to={`/research?ticker=${symbol}`} style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
                <Icon name="auto_awesome" size={16} /> Research
              </Link>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 300px', gap: 20, alignItems: 'start' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* CHART */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '20px 24px', borderBottom: '1px solid #292524' }}>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 6 }}>Market Value</div>
                    <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: isMobile ? 24 : 32, fontWeight: 600, letterSpacing: '-0.03em' }}>{formatCurrency(holding.market_value, holding.currency ?? 'USD')}</div>
                  </div>
                  <div style={{ textAlign: 'end' }}>
                    <div style={{ fontSize: 15, fontWeight: 600, color: gain ? '#22c55e' : '#ef4444' }}>
                      <bdi>{gain ? '+' : ''}{formatCurrency(holding.pnl, holding.currency ?? 'USD')}</bdi>
                    </div>
                    <div style={{ fontSize: 12, color: gain ? '#22c55e' : '#ef4444' }}>
                      <bdi>{gain ? '+' : ''}{holding.pnl_pct}%</bdi> all time
                    </div>
                  </div>
                </div>
              </div>
              <div style={{ padding: '16px 24px' }}>
                <LineChart data={chartData} gain={gain} />
              </div>
            </div>

            {/* TRANSACTIONS */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 24px', borderBottom: '1px solid #292524' }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>Transactions</div>
                <Link to={`/portfolio/${id}/add`} style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Icon name="add" size={14} /> Add
                </Link>
              </div>
              <div>
                {transactions.map((t: any) => (
                  <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)' }}>
                    <div style={{ width: 36, height: 36, borderRadius: 9, background: t.type === 'BUY' ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', border: `1px solid ${t.type === 'BUY' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Icon name={t.type === 'BUY' ? 'add' : 'remove'} size={16} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{t.type} {t.shares} shares</div>
                      <div style={{ fontSize: 12, color: '#a8a29e' }}>@ {formatCurrency(t.price, holding.currency ?? 'USD')} each &nbsp;&middot;&nbsp; {t.date}</div>
                    </div>
                    <div style={{ textAlign: 'end' }}>
                      <div style={{ fontVariantNumeric: 'tabular-nums', fontSize: 13, fontWeight: 500 }}>{formatCurrency(t.total || t.shares * t.price, holding.currency ?? 'USD')}</div>
                    </div>
                    <button
                      onClick={() => confirm('Delete this transaction?') && deleteMutation.mutate(t.id)}
                      style={{ width: 28, height: 28, borderRadius: 7, border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.05)', color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
                    >
                      <Icon name="delete" size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* STATS CARD */}
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #292524', fontSize: 13, fontWeight: 600 }}>Position Details</div>
            <div>
              {[
                { label: 'Shares held', val: String(holding.shares) },
                { label: 'Avg cost basis', val: formatCurrency(holding.avg_cost, holding.currency ?? 'USD') },
                { label: 'Current price', val: formatCurrency(holding.current_price, holding.currency ?? 'USD') },
                { label: 'Market value', val: formatCurrency(holding.market_value, holding.currency ?? 'USD') },
                { label: 'Unrealized P&L', val: `${gain ? '+' : ''}${formatCurrency(holding.pnl, holding.currency ?? 'USD')}`, color: gain ? '#22c55e' : '#ef4444' },
                { label: 'Return', val: `${gain ? '+' : ''}${holding.pnl_pct}%`, color: gain ? '#22c55e' : '#ef4444' },
                { label: 'Cost basis total', val: formatCurrency(holding.shares * holding.avg_cost, holding.currency ?? 'USD') },
              ].map(({ label, val, color }) => (
                <div key={label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)' }}>
                  <span style={{ fontSize: 13, color: '#a8a29e' }}>{label}</span>
                  <span style={{ fontSize: 13, fontWeight: 500, fontVariantNumeric: 'tabular-nums', color: color || '#fafaf9' }}><bdi>{val}</bdi></span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
