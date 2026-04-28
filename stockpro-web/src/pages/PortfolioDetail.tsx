import { useState, useMemo } from 'react'
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import Skeleton from '../components/Skeleton'
import { useApiClient } from '../api/client'
import { useLanguage } from '../LanguageContext'
import { useBreakpoint } from '../hooks/useBreakpoint'
import { formatCurrency, formatCompact } from '../utils/currency'

const RANGES = ['1W', '1M', '3M', 'YTD', '1Y']

type SortKey = 'symbol' | 'shares' | 'avg_cost' | 'current_price' | 'market_value' | 'pnl' | 'pnl_pct'
type SortDir = 'asc' | 'desc'
type AssetFilter = 'all' | 'stock' | 'crypto'

const COLUMNS: { label: string; key: SortKey; align: 'left' | 'right' }[] = [
  { label: 'Holding', key: 'symbol', align: 'left' },
  { label: 'Shares', key: 'shares', align: 'right' },
  { label: 'Avg Cost', key: 'avg_cost', align: 'right' },
  { label: 'Current Price', key: 'current_price', align: 'right' },
  { label: 'Market Value', key: 'market_value', align: 'right' },
  { label: 'P&L', key: 'pnl', align: 'right' },
  { label: 'Return', key: 'pnl_pct', align: 'right' },
]

const CRYPTO_SYMBOLS = new Set([
  'BTC', 'ETH', 'SOL', 'ADA', 'XRP', 'DOGE', 'DOT', 'AVAX', 'MATIC', 'LINK',
  'UNI', 'AAVE', 'ATOM', 'LTC', 'BCH', 'ALGO', 'FIL', 'NEAR', 'APT', 'ARB',
  'OP', 'SUI', 'SEI', 'TIA', 'INJ', 'SHIB', 'PEPE', 'WIF', 'BONK', 'RENDER',
])

function inferAssetType(symbol: string): 'stock' | 'crypto' {
  const s = symbol.toUpperCase().replace(/-USD$/, '')
  if (CRYPTO_SYMBOLS.has(s)) return 'crypto'
  if (symbol.endsWith('-USD') || symbol.endsWith('-usd')) return 'crypto'
  return 'stock'
}

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
          <text x={padLeft - 8} y={y + 4} fill="#78716c" fontSize="10" textAnchor="end" fontFamily="Inter, Heebo, sans-serif">{formatCompact(val)}</text>
        </g>
      ))}
      {/* X labels */}
      {xLabels.map(({ label, x }) => (
        <text key={label + x} x={x} y={h - 4} fill="#78716c" fontSize="10" textAnchor="middle" fontFamily="Inter, Heebo, sans-serif">{label}</text>
      ))}
      <polygon points={`${padLeft},${h - padBottom} ${pts} ${lastX},${h - padBottom}`} fill="url(#chartGrad)" />
      <polyline points={pts} stroke={color} strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

const fmtUsd = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)

function CashModal({ portfolioId, currentBalance, onClose }: { portfolioId: string; currentBalance: number; onClose: () => void }) {
  const [action, setAction] = useState<'deposit' | 'withdraw'>('deposit')
  const [amount, setAmount] = useState('')
  const [error, setError] = useState('')
  const api = useApiClient()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async () => {
      const val = parseFloat(amount)
      if (isNaN(val) || val <= 0) throw new Error('Enter a positive amount')
      const res = await api.post(`/api/portfolio/${portfolioId}/cash`, { action, amount: val })
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || 'Failed')
      return data
    },
    onSuccess: (data) => {
      const newBalance = data.cash_balance
      queryClient.setQueryData(['portfolio-prices', portfolioId], (old: any) =>
        old ? { ...old, cash_balance: newBalance } : old
      )
      queryClient.setQueryData(['portfolio-detail', portfolioId], (old: any) =>
        old?.summary ? { ...old, summary: { ...old.summary, cash_balance: newBalance } } : old
      )
      toast.success(action === 'deposit' ? 'Cash deposited' : 'Cash withdrawn')
      onClose()
    },
    onError: (e: Error) => setError(e.message),
  })

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: 32, width: 400, maxWidth: '90vw' }}>
        <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 20, fontWeight: 600, marginBottom: 8, letterSpacing: '-0.02em' }}>Deposit / Withdraw</h2>
        <p style={{ fontSize: 12, color: '#a8a29e', marginBottom: 20 }}>Current balance: <span style={{ fontVariantNumeric: 'tabular-nums', color: '#fafaf9', fontWeight: 600 }}>{fmtUsd(currentBalance)}</span></p>
        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          {(['deposit', 'withdraw'] as const).map(a => (
            <label key={a} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="radio" checked={action === a} onChange={() => setAction(a)} style={{ accentColor: '#d6d3d1' }} />
              <span style={{ fontSize: 13, color: '#fafaf9', textTransform: 'capitalize' }}>{a}</span>
            </label>
          ))}
        </div>
        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#a8a29e', marginBottom: 6 }}>Amount ($)</label>
          <input
            autoFocus
            value={amount}
            onChange={e => { setAmount(e.target.value); setError('') }}
            onKeyDown={e => e.key === 'Enter' && mutation.mutate()}
            placeholder="0.00"
            inputMode="decimal"
            style={{ width: '100%', background: '#232120', border: '1px solid #292524', borderRadius: 10, padding: '10px 14px', color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 14, fontVariantNumeric: 'tabular-nums', outline: 'none', boxSizing: 'border-box' }}
          />
        </div>
        {error && <p style={{ fontSize: 12, color: '#ef4444', marginBottom: 12 }}>{error}</p>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', cursor: 'pointer', fontSize: 13 }}>Cancel</button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: '#d6d3d1', color: '#0c0a09', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
          >
            {mutation.isPending ? 'Saving...' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}

function EnableCashBanner({ portfolioId }: { portfolioId: string }) {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: async () => {
      const res = await api.post(`/api/portfolio/${portfolioId}/toggle-cash`, {})
      const data = await res.json()
      if (!data.ok) throw new Error(data.error || 'Failed')
    },
    onSuccess: () => {
      queryClient.setQueryData(['portfolio-prices', portfolioId], (old: any) =>
        old ? { ...old, track_cash: true, cash_balance: old.cash_balance ?? 0 } : old
      )
      queryClient.setQueryData(['portfolio-detail', portfolioId], (old: any) =>
        old?.summary ? { ...old, summary: { ...old.summary, track_cash: true } } : old
      )
      toast.success('Cash tracking enabled')
    },
    onError: () => toast.error('Failed to enable cash tracking'),
  })

  return (
    <tr>
      <td colSpan={7} style={{ padding: '12px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#232120', borderRadius: 8, padding: '10px 16px' }}>
          <span style={{ fontSize: 13, color: '#a8a29e' }}>Cash tracking is disabled for this portfolio.</span>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            style={{ fontSize: 12, fontWeight: 600, padding: '6px 12px', borderRadius: 6, border: 'none', background: '#d6d3d1', color: '#0c0a09', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <Icon name="payments" size={14} />
            {mutation.isPending ? 'Enabling...' : 'Enable Cash Tracking'}
          </button>
        </div>
      </td>
    </tr>
  )
}

export default function PortfolioDetail() {
  const { id } = useParams()
  const [range, setRange] = useState('1M')
  const [showCashModal, setShowCashModal] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('market_value')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [searchText, setSearchText] = useState('')
  const [assetFilter, setAssetFilter] = useState<AssetFilter>('all')
  const api = useApiClient()
  const { t } = useTranslation()
  const { lang } = useLanguage()
  const { isMobile } = useBreakpoint()

  const locale = lang === 'he' ? 'he-IL' : 'en-US'
  const fmt = (n: number, currency = 'USD') => formatCurrency(n, currency, locale)

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
    asset_type: h.asset_type ?? inferAssetType(h.symbol),
  }))

  const displayHoldings = useMemo(() => {
    let filtered = holdings
    if (searchText) {
      const q = searchText.toLowerCase()
      filtered = filtered.filter((h: any) =>
        h.symbol.toLowerCase().includes(q) || h.name.toLowerCase().includes(q)
      )
    }
    if (assetFilter !== 'all') {
      filtered = filtered.filter((h: any) => h.asset_type === assetFilter)
    }
    return [...filtered].sort((a: any, b: any) => {
      if (sortKey === 'symbol') {
        const cmp = a.symbol.localeCompare(b.symbol)
        return sortDir === 'asc' ? cmp : -cmp
      }
      const av = Number(a[sortKey]) || 0
      const bv = Number(b[sortKey]) || 0
      return sortDir === 'asc' ? av - bv : bv - av
    })
  }, [holdings, searchText, assetFilter, sortKey, sortDir])

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir(key === 'symbol' ? 'asc' : 'desc')
    }
  }

  const isFiltered = searchText !== '' || assetFilter !== 'all'

  const transactionsRaw = txData?.transactions || []
  const displayTransactions = useMemo(() => {
    if (!isFiltered) return transactionsRaw
    const symbolSet = new Set(displayHoldings.map((h: any) => h.symbol.toUpperCase()))
    return transactionsRaw.filter((t: any) => symbolSet.has((t.symbol || '').toUpperCase()))
  }, [transactionsRaw, displayHoldings, isFiltered])

  const portfolioName = portfolioData?.portfolio?.name || 'Portfolio'

  const filteredValue = useMemo(() => displayHoldings.reduce((s: number, h: any) => s + (h.market_value || 0), 0), [displayHoldings])
  const filteredPnl = useMemo(() => displayHoldings.reduce((s: number, h: any) => s + (h.pnl || 0), 0), [displayHoldings])
  const filteredCostBasis = useMemo(() => displayHoldings.reduce((s: number, h: any) => s + (h.avg_cost * h.shares || 0), 0), [displayHoldings])

  const totalValue = isFiltered ? filteredValue : (pricesData?.total_market_value ?? 0)
  const pnl = isFiltered ? filteredPnl : (pricesData?.total_unrealized_gain ?? 0)
  const pnlPct = isFiltered
    ? (filteredCostBasis > 0 ? (filteredPnl / filteredCostBasis) * 100 : 0)
    : (pricesData?.total_unrealized_gain_pct ?? 0)
  const trackCash = pricesData?.track_cash ?? portfolioData?.summary?.track_cash ?? false
  const cashBalance = pricesData?.cash_balance ?? portfolioData?.summary?.cash_balance ?? 0
  // Per-ticker history — always fetched so the chart can recompute deterministically
  // for any filter/sort combination without waiting on a separate request.
  const holdingSymbols = useMemo(() => holdings.map((h: any) => h.symbol as string), [holdings])
  const tickerHistories = useQueries({
    queries: holdingSymbols.map((symbol: string) => ({
      queryKey: ['ticker-history', symbol, range],
      queryFn: async () => {
        const res = await api.get(`/api/ticker/${symbol}/history?range=${range}`)
        if (!res.ok) return { symbol, history: [] }
        const data = await res.json()
        return { symbol, history: data.history || [] }
      },
      staleTime: 5 * 60 * 1000,
    })),
  })

  // Stable signature so useMemo only recomputes when the underlying data actually changes
  // (useQueries returns a new array reference every render).
  const tickerDataSig = tickerHistories
    .map(q => {
      const d = q.data as { symbol?: string; history?: any[] } | undefined
      return `${d?.symbol ?? ''}:${d?.history?.length ?? 0}`
    })
    .join('|')

  // Portfolio-level history is used as a fallback while per-ticker queries are loading
  // (so users see *something*, scaled to the current filtered set).
  const historyRaw = historyData?.history || []

  const { chartData, chartDates } = useMemo(() => {
    // Reconstruct value series from per-ticker close * shares for the visible holdings.
    // Same code path for filtered and unfiltered → guarantees the chart re-renders
    // whenever displayHoldings changes.
    const sharesMap = new Map<string, number>(
      displayHoldings.map((h: any) => [h.symbol, Number(h.shares) || 0])
    )
    const dateMap = new Map<string, number>()

    for (const q of tickerHistories) {
      const d = q.data as { symbol?: string; history?: any[] } | undefined
      if (!d || !d.symbol || !sharesMap.has(d.symbol)) continue
      const shares = sharesMap.get(d.symbol) || 0
      if (shares === 0) continue
      for (const pt of (d.history || [])) {
        if (!pt?.date) continue
        const val = (Number(pt.close) || 0) * shares
        dateMap.set(pt.date, (dateMap.get(pt.date) || 0) + val)
      }
    }

    const sorted = [...dateMap.entries()].sort((a, b) => a[0].localeCompare(b[0]))
    let data = sorted.map(([, v]) => v)
    let dates = sorted.map(([d]) => d)

    // Fallback: per-ticker data not ready yet → scale portfolio history by the
    // ratio of filtered market value to total market value so the chart is
    // populated *and* changes when filters change.
    if (data.length < 2 && historyRaw.length >= 2) {
      const totalMv = pricesData?.total_market_value || 0
      const filteredMv = displayHoldings.reduce(
        (s: number, h: any) => s + (Number(h.market_value) || 0), 0
      )
      const scale = totalMv > 0 ? (filteredMv / totalMv) : 1
      data = historyRaw
        .map((h: any) => (Number(h.value ?? h.close) || 0) * scale)
      dates = historyRaw.map((h: any) => h.date || '')
      // Drop trailing zero points (matches old behavior) but keep date alignment.
      const filtered = data
        .map((v: number, i: number) => ({ v, d: dates[i] }))
        .filter((x: { v: number; d: string }) => x.v > 0 && x.d)
      data = filtered.map((x: { v: number; d: string }) => x.v)
      dates = filtered.map((x: { v: number; d: string }) => x.d)
    }

    return { chartData: data, chartDates: dates }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayHoldings, tickerDataSig, historyRaw, pricesData?.total_market_value])

  const chartLoading = tickerHistories.length > 0
    && tickerHistories.every(q => q.isLoading)
    && historyLoading

  const dotColors = ['#60a5fa', '#a78bfa', '#22c55e', '#f59e0b', '#f472b6']

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      {showCashModal && <CashModal portfolioId={id!} currentBalance={cashBalance} onClose={() => setShowCashModal(false)} />}
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
            <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>{portfolioName}</h1>
            <div style={{ fontSize: 13, color: '#a8a29e' }}>{holdings.length + (trackCash ? 1 : 0)} {t('portfolioDetail.holdings')}</div>
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20, minWidth: 0 }}>

            {/* CHART CARD */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '20px 24px', borderBottom: '1px solid #292524' }}>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 4 }}>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 6 }}>
                      {t('portfolioDetail.portfolioValue')}{isFiltered && <span style={{ marginLeft: 6, fontSize: 10, color: '#78716c', textTransform: 'none', letterSpacing: 'normal' }}>(filtered)</span>}
                    </div>
                    <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: isMobile ? 26 : 36, fontWeight: 600, letterSpacing: '-0.03em' }}>{fmt(totalValue)}</div>
                  </div>
                  <div style={{ textAlign: 'end' }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                      <bdi>{pnl >= 0 ? '+' : ''}{fmt(pnl)}</bdi>
                    </div>
                    <div style={{ fontSize: 13, color: pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                      <bdi>{pnl >= 0 ? '+' : ''}{Number(pnlPct).toFixed(2)}%</bdi> all time
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
                <LineChart data={chartData} dates={chartDates} gain={pnl >= 0} loading={chartLoading} locale={locale} />
              </div>
            </div>

            {/* HOLDINGS TABLE */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ padding: '16px 24px', borderBottom: '1px solid #292524' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{t('portfolioDetail.holdings')}</div>
                  <Link to={`/portfolio/${id}/add`} style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Icon name="add" size={14} /> {t('portfolioDetail.add')}
                  </Link>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ position: 'relative', maxWidth: 260, flex: 1 }}>
                    <Icon name="search" size={16} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#78716c', pointerEvents: 'none' }} />
                    <input
                      value={searchText}
                      onChange={e => setSearchText(e.target.value)}
                      placeholder="Search holdings..."
                      style={{ width: '100%', background: '#232120', border: '1px solid #292524', borderRadius: 8, padding: '7px 12px 7px 32px', color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 12.5, outline: 'none', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {(['all', 'stock', 'crypto'] as const).map(f => (
                      <button
                        key={f}
                        onClick={() => setAssetFilter(f)}
                        style={{ padding: '5px 12px', borderRadius: 7, fontSize: 12, fontWeight: 500, border: 'none', cursor: 'pointer', background: assetFilter === f ? 'rgba(214,211,209,0.12)' : 'transparent', color: assetFilter === f ? '#fafaf9' : '#a8a29e', transition: 'all 0.15s', textTransform: 'capitalize' }}
                      >
                        {f === 'all' ? 'All' : f === 'stock' ? 'Stocks' : 'Crypto'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: isMobile ? 640 : undefined }}>
                <thead>
                  <tr style={{ padding: '0 24px' }}>
                    {COLUMNS.map(col => {
                      const active = sortKey === col.key
                      const label = col.key === 'current_price' ? t('portfolioDetail.currentPrice') : col.label
                      return (
                        <th
                          key={col.key}
                          onClick={() => handleSort(col.key)}
                          style={{ fontSize: 10.5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: active ? '#fafaf9' : '#a8a29e', textAlign: col.align === 'left' ? 'start' : 'end', padding: '12px 24px', borderBottom: '1px solid #292524', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            {label}
                            <Icon
                              name={active ? (sortDir === 'asc' ? 'arrow_upward' : 'arrow_downward') : 'swap_vert'}
                              size={14}
                              style={{ opacity: active ? 1 : 0.3 }}
                            />
                          </span>
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {trackCash ? (
                    <tr>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', fontSize: 13.5 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#a8a29e', flexShrink: 0 }} />
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9' }}>CASH</div>
                            <div style={{ fontSize: 11.5, color: '#a8a29e' }}>Cash</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'right', color: '#57534e' }}>--</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'right', color: '#57534e' }}>--</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'right', color: '#57534e' }}>--</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: '#fafaf9', fontWeight: 600 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
                          {fmt(cashBalance)}
                          <button
                            onClick={() => setShowCashModal(true)}
                            style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 8px', fontSize: 11, fontWeight: 500, background: '#232120', border: '1px solid #292524', borderRadius: 6, color: '#a8a29e', cursor: 'pointer' }}
                          >
                            <Icon name="swap_vert" size={14} />
                          </button>
                        </div>
                      </td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'right', color: '#57534e' }}>--</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'right', color: '#57534e' }}>--</td>
                    </tr>
                  ) : (
                    <EnableCashBanner portfolioId={id!} />
                  )}
                  {displayHoldings.length === 0 && holdings.length > 0 && (
                    <tr>
                      <td colSpan={7} style={{ padding: '24px', textAlign: 'center', fontSize: 13, color: '#a8a29e' }}>
                        No holdings match your search.
                      </td>
                    </tr>
                  )}
                  {displayHoldings.map((h: any, i: number) => (
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
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{fmt(h.avg_cost, h.currency ?? 'USD')}</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{h.current_price != null ? fmt(h.current_price, h.currency ?? 'USD') : <span style={{ color: '#57534e' }}>--</span>}</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{fmt(h.market_value, h.currency ?? 'USD')}</td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: h.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                        <bdi>{h.pnl >= 0 ? '+' : ''}{fmt(h.pnl, h.currency ?? 'USD')}</bdi>
                      </td>
                      <td style={{ padding: '14px 24px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end' }}>
                        <span style={{ display: 'inline-flex', fontSize: 12, fontWeight: 500, padding: '3px 8px', borderRadius: 999, background: h.pnl_pct >= 0 ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)', color: h.pnl_pct >= 0 ? '#22c55e' : '#ef4444', border: `1px solid ${h.pnl_pct >= 0 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}` }}>
                          <bdi>{h.pnl_pct >= 0 ? '+' : ''}{Number(h.pnl_pct).toFixed(2)}%</bdi>
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
                {displayTransactions.length === 0 ? (
                  <div style={{ padding: '16px 20px', fontSize: 12, color: '#a8a29e' }}>{isFiltered ? 'No transactions match your filter.' : t('portfolioDetail.noTransactions')}</div>
                ) : displayTransactions.map((tx: any) => {
                  // API fields: transaction_id, symbol, transaction_type, quantity, price_per_unit, transaction_date
                  const txType = (tx.transaction_type || tx.type || 'BUY').toUpperCase()
                  const isBuy = txType === 'BUY'
                  const dateStr = tx.transaction_date ? new Date(tx.transaction_date).toLocaleDateString(locale, { month: 'short', day: 'numeric' }) : (tx.date || '')
                  return (
                  <div key={tx.transaction_id || tx.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)' }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: isBuy ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', border: `1px solid ${isBuy ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Icon name={isBuy ? 'add' : 'remove'} size={16} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{txType} {tx.symbol}</div>
                      <div style={{ fontSize: 11.5, color: '#a8a29e' }}>{tx.quantity ?? tx.shares} shares @ {fmt(tx.price_per_unit ?? tx.price ?? 0)}</div>
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
