import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useBreakpoint } from '../hooks/useBreakpoint'

function Sparkline({ gain = true }: { gain?: boolean }) {
  const color = gain ? '#22c55e' : '#ef4444'
  const upPts = '0,44 40,38 80,40 120,30 160,24 200,28 240,18 280,12 320,16 360,8 400,6'
  const downPts = '0,10 60,14 120,20 160,18 200,24 250,32 300,28 340,36 400,40'
  const points = gain ? upPts : downPts
  const gradId = gain ? 'g-up' : 'g-down'
  return (
    <svg viewBox="0 0 400 56" preserveAspectRatio="none" fill="none" style={{ width: '100%', height: 56 }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={gain ? '0.18' : '0.15'} />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`${points} 400,56 0,56`} fill={`url(#${gradId})`} />
      <polyline points={points} stroke={color} strokeWidth="1.5" fill="none" strokeLinejoin="round" />
    </svg>
  )
}

interface NewPortfolioModalProps {
  onClose: () => void
}

function NewPortfolioModal({ onClose }: NewPortfolioModalProps) {
  const [name, setName] = useState('')
  const [trackCash, setTrackCash] = useState(true)
  const [cashBalance, setCashBalance] = useState('')
  const api = useApiClient()
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  const mutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = { name, track_cash: trackCash }
      if (trackCash && cashBalance.trim()) {
        body.cash_balance = parseFloat(cashBalance) || 0
      }
      const res = await api.post('/api/portfolios', body)
      if (!res.ok) throw new Error('Failed to create portfolio')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      toast.success(t('portfolio.toasts.created'))
      onClose()
    },
    onError: () => toast.error(t('portfolio.toasts.createFailed')),
  })

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: 32, width: 400, maxWidth: '90vw' }}>
        <h2 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 20, fontWeight: 600, marginBottom: 20, letterSpacing: '-0.02em' }}>{t('portfolio.newPortfolio')}</h2>
        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#a8a29e', marginBottom: 6, letterSpacing: '0.02em' }}>{t('portfolio.portfolioName')}</label>
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && name.trim() && mutation.mutate()}
            placeholder="e.g. Tech Growth"
            style={{ width: '100%', background: '#232120', border: '1px solid #292524', borderRadius: 10, padding: '10px 14px', color: '#fafaf9', fontFamily: 'Inter, Heebo, sans-serif', fontSize: 14, outline: 'none', boxSizing: 'border-box' }}
          />
        </div>
        <div style={{ marginBottom: trackCash ? 12 : 20 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={trackCash} onChange={e => setTrackCash(e.target.checked)} style={{ accentColor: '#d6d3d1' }} />
            <span style={{ fontSize: 13, color: '#d6d3d1' }}>Track cash in this portfolio</span>
          </label>
        </div>
        {trackCash && (
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#a8a29e', marginBottom: 6 }}>Initial cash balance (optional)</label>
            <input
              value={cashBalance}
              onChange={e => setCashBalance(e.target.value)}
              placeholder="0"
              inputMode="decimal"
              style={{ width: '100%', background: '#232120', border: '1px solid #292524', borderRadius: 10, padding: '10px 14px', color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 14, fontVariantNumeric: 'tabular-nums', outline: 'none', boxSizing: 'border-box' }}
            />
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', cursor: 'pointer', fontSize: 13 }}>{t('portfolio.cancel')}</button>
          <button
            onClick={() => name.trim() && mutation.mutate()}
            disabled={!name.trim() || mutation.isPending}
            style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: name.trim() ? '#d6d3d1' : '#292524', color: name.trim() ? '#0c0a09' : '#a8a29e', cursor: name.trim() ? 'pointer' : 'not-allowed', fontSize: 13, fontWeight: 600 }}
          >
            {mutation.isPending ? t('portfolio.creating') : t('portfolio.createPortfolio')}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function PortfolioList() {
  const [showModal, setShowModal] = useState(false)
  const api = useApiClient()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { isMobile } = useBreakpoint()

  const fmt = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)

  const { data, isLoading } = useQuery({
    queryKey: ['portfolios'],
    queryFn: async () => {
      const res = await api.get('/api/portfolios/prices')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // /api/portfolios/prices returns:
  // portfolios: [{portfolio_id, total_market_value, total_unrealized_gain, total_unrealized_gain_pct, day_change}]
  // totals: {total_value, total_pnl, day_change}
  const portfoliosRaw = data?.portfolios || []
  const totals = data?.totals || {}
  // Normalize for display
  const portfolios = portfoliosRaw.map((p: any) => ({
    ...p,
    id: p.portfolio_id || p.id,
    value: p.total_market_value ?? p.value ?? 0,
    pnl: p.total_unrealized_gain ?? p.pnl ?? 0,
    pnl_pct: p.total_unrealized_gain_pct != null ? Number(p.total_unrealized_gain_pct).toFixed(1) : (p.pnl_pct ?? 0),
  }))

  const dotColors = ['#60a5fa', '#a78bfa', '#22c55e', '#f59e0b', '#f472b6']

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      {showModal && <NewPortfolioModal onClose={() => setShowModal(false)} />}
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: isMobile ? '20px 16px 60px' : '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 36 }}>
          <div>
            <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>{t('portfolio.myPortfolios')}</div>
            <div style={{ fontSize: 13, color: '#a8a29e' }}>
              {portfolios.length} {t('portfolio.portfolios')} &nbsp;&middot;&nbsp; {t('portfolio.lastUpdated')}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => setShowModal(true)}
              style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <Icon name="add" size={16} />
              {t('portfolio.newPortfolio')}
            </button>
          </div>
        </div>

        {/* AGGREGATE STRIP */}
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)', gap: 1, background: '#292524', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden', marginBottom: 36 }}>
          {[
            { label: t('portfolio.totalValue'), val: totals.total_value != null ? fmt(totals.total_value) : '-', sub: '', subClass: 'muted' },
            { label: t('portfolio.totalPnl'), val: totals.total_pnl != null ? ((totals.total_pnl >= 0 ? '+' : '') + fmt(totals.total_pnl)) : '-', valColor: totals.total_pnl >= 0 ? '#22c55e' : '#ef4444', sub: t('portfolio.allTime'), subClass: totals.total_pnl >= 0 ? 'up' : 'down' },
            { label: t('portfolio.todaysChange'), val: totals.day_change != null ? fmt(totals.day_change) : '-', valColor: totals.day_change >= 0 ? '#22c55e' : '#ef4444', sub: t('portfolio.vsYesterday'), subClass: totals.day_change >= 0 ? 'up' : 'down' },
            { label: t('portfolio.portfolios'), val: String(portfolios.length), sub: `${portfolios.length} ${t('portfolio.portfolios')} ${t('portfolio.tracked')}`, subClass: 'muted' },
          ].map(({ label, val, valColor, sub, subClass }) => (
            <div key={label} style={{ background: '#1c1917', padding: '20px 24px' }}>
              <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 8 }}>{label}</div>
              <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 28, fontWeight: 600, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums', color: valColor || '#fafaf9' }}><bdi>{val}</bdi></div>
              <div style={{ fontSize: 12, marginTop: 4, fontVariantNumeric: 'tabular-nums', color: subClass === 'up' ? '#22c55e' : subClass === 'down' ? '#ef4444' : '#a8a29e' }}>{sub}</div>
            </div>
          ))}
        </div>

        {/* PORTFOLIO GRID */}
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)', gap: 16 }}>
          {isLoading ? (
            [1, 2].map(i => (
              <div key={i} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, height: 280 }} />
            ))
          ) : (
            <>
              {portfolios.map((p: any) => {
                const gain = (p.pnl_pct || 0) >= 0
                return (
                  <div
                    key={p.id}
                    onClick={() => navigate(`/portfolio/${p.id || p.portfolio_id}`)}
                    style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, overflow: 'hidden', cursor: 'pointer', transition: 'border-color 0.2s' }}
                  >
                    <div style={{ padding: '22px 24px 18px', borderBottom: '1px solid #292524', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                      <div>
                        <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em', marginBottom: 4 }}>{p.name}</div>
                        <div style={{ fontSize: 12, color: '#a8a29e', display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span>{p.holdings_count || 0} {t('portfolio.holdings')}</span>
                          <span>&middot;</span>
                          <span style={{ fontSize: 11, fontWeight: 500, padding: '3px 9px', borderRadius: 999, border: '1px solid #292524', color: '#a8a29e', background: '#232120' }}>{p.type || t('portfolio.stocks')}</span>
                        </div>
                      </div>
                    </div>
                    <div style={{ padding: '22px 24px' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 16 }}>
                        <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 32, fontWeight: 600, letterSpacing: '-0.03em', fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
                          {fmt(p.value || 0)}
                        </div>
                        <span style={{ fontSize: 13, fontWeight: 500, padding: '5px 12px', borderRadius: 999, background: gain ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)', color: gain ? '#22c55e' : '#ef4444', border: `1px solid ${gain ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`, fontVariantNumeric: 'tabular-nums' }}>
                          <bdi>{gain ? '+' : ''}{p.pnl_pct || 0}%</bdi> {t('portfolio.allTimeLabel')}
                        </span>
                      </div>
                      <div style={{ marginBottom: 18, height: 56 }}>
                        <Sparkline gain={gain} />
                      </div>
                      {p.holdings && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{ display: 'flex', gap: 4 }}>
                            {p.holdings.slice(0, 5).map((h: any, i: number) => (
                              <div key={h.symbol} style={{ width: 20, height: 20, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 7, fontWeight: 700, fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', background: `${dotColors[i % dotColors.length]}26`, color: dotColors[i % dotColors.length] }}>
                                {h.symbol.slice(0, 2)}
                              </div>
                            ))}
                          </div>
                          {p.holdings_count > 5 && (
                            <div style={{ fontSize: 12, color: '#a8a29e', marginInlineStart: 'auto' }}>{t('portfolio.more', { count: p.holdings_count - 5 })}</div>
                          )}
                        </div>
                      )}
                    </div>
                    <div style={{ padding: '14px 24px', borderTop: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ fontSize: 12, color: '#a8a29e', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Icon name="schedule" size={14} />
                        {t('portfolio.updatedJustNow')}
                      </div>
                      <div style={{ fontSize: 12, color: '#a8a29e', display: 'flex', alignItems: 'center', gap: 4 }}>
                        {t('portfolio.viewDetails')} <Icon name="chevron_right" size={14} />
                      </div>
                    </div>
                  </div>
                )
              })}

              {/* CREATE NEW */}
              <div
                onClick={() => setShowModal(true)}
                style={{ border: '2px dashed #292524', borderRadius: 16, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '48px 24px', textAlign: 'center', minHeight: 240, transition: 'border-color 0.2s' }}
              >
                <Icon name="add_circle" size={32} />
                <h3 style={{ fontSize: 15, fontWeight: 600 }}>{t('portfolio.createAPortfolio')}</h3>
                <p style={{ fontSize: 13, color: '#a8a29e', maxWidth: 240 }}>{t('portfolio.createDesc')}</p>
              </div>
            </>
          )}
        </div>

        {/* IMPORT ROW */}
        <div style={{ marginTop: 24, padding: '18px 24px', background: '#1c1917', border: '1px solid #292524', borderRadius: 14, display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Icon name="upload_file" size={20} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>{t('portfolio.importFromCsv')}</div>
            <div style={{ fontSize: 12.5, color: '#a8a29e' }}>{t('portfolio.importDesc')}</div>
          </div>
          {portfolios.length > 0 && (
            <Link to={`/portfolio/${portfolios[0].id}/import`} style={{ background: 'transparent', border: '1px solid #292524', color: '#a8a29e', fontSize: 13, fontWeight: 500, padding: '8px 16px', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none', whiteSpace: 'nowrap' }}>
              <Icon name="upload" size={16} />
              {t('portfolio.importCsv')}
            </Link>
          )}
        </div>

      </main>
    </div>
  )
}
