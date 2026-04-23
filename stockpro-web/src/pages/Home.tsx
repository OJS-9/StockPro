import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import { useUser } from '@clerk/clerk-react'
import { useTranslation } from 'react-i18next'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useLanguage } from '../LanguageContext'
import { useBreakpoint } from '../hooks/useBreakpoint'

function Sparkline({ gain = true }: { gain?: boolean }) {
  const color = gain ? '#22c55e' : '#ef4444'
  const points = gain
    ? '0,50 15,42 28,46 40,32 55,28 65,34 75,20 88,14 100,18 120,10'
    : '0,10 15,18 28,22 40,20 55,28 65,32 75,28 88,36 100,40 120,44'
  return (
    <svg viewBox="0 0 120 60" preserveAspectRatio="none" fill="none" style={{ width: '100%', height: '100%' }}>
      <defs>
        <linearGradient id={`sg-${gain}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.4" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={points} stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" fill="none" />
      <polygon points={`${points} 120,60 0,60`} fill={`url(#sg-${gain})`} opacity="0.5" />
    </svg>
  )
}

function Skeleton({ w = '100%', h = 20 }: { w?: string | number; h?: number }) {
  return <div style={{ width: w, height: h, borderRadius: 8, background: '#1c1917', opacity: 0.6 }} />
}

export default function Home() {
  const { user } = useUser()
  const api = useApiClient()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { lang } = useLanguage()
  const { isMobile } = useBreakpoint()
  const locale = lang === 'he' ? 'he-IL' : 'en-US'
  const fmt = (n: number) => new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' }).format(n)
  const [ticker, setTicker] = useState('')
  const [changeMode, setChangeMode] = useState<'D' | 'W'>('D')

  const { data, isLoading } = useQuery({
    queryKey: ['home'],
    queryFn: async () => {
      const res = await api.get('/api/home')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const firstName = user?.firstName || 'there'
  const hour = new Date().getHours()
  const greeting = hour < 12 ? t('home.goodMorning') : hour < 17 ? t('home.goodAfternoon') : t('home.goodEvening')

  const handleResearch = () => {
    if (ticker.trim()) navigate(`/research?ticker=${ticker.trim().toUpperCase()}`)
    else navigate('/research')
  }

  // /api/home returns: portfolio_totals, holdings_preview, recent_reports,
  // active_alerts_count, watchlist_preview, news
  const totals = data?.portfolio_totals || {}
  const holdings = data?.holdings_preview || []
  const watchlist = data?.watchlist_preview || []
  const alertsCount = data?.active_alerts_count ?? null
  const news = data?.news || []
  const recentReports = data?.recent_reports || []
  // Recent tickers derived from recent reports
  const recentTickers: string[] = Array.from(
    new Set((recentReports as any[]).map((r: any) => r.ticker || r.symbol).filter(Boolean))
  ).slice(0, 3) as string[]

  if (isLoading) {
    return (
      <div style={{ background: '#0c0a09', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 28, fontFamily: 'Nunito, sans-serif', fontWeight: 700, color: '#d6d3d1', letterSpacing: '-0.02em' }}>StockPro</div>
        <div style={{ width: 32, height: 32, border: '3px solid #292524', borderTopColor: '#d6d3d1', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
      </div>
    )
  }

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1240, margin: '0 auto', padding: isMobile ? '20px 16px 60px' : '36px 48px 80px' }}>

        {/* GREETING */}
        <div style={{ marginBottom: 32, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 24, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>
              {greeting}, {firstName}
            </h1>
            <p style={{ fontSize: 13, color: '#a8a29e' }}>
              {new Date().toLocaleDateString(locale, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          </div>
        </div>

        {/* RESEARCH BAR */}
        <div
          style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: '0 20px', display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32, height: 54, transition: 'border-color 0.2s' }}
        >
          <Icon name="auto_awesome" size={20} />
          <input
            value={ticker}
            onChange={e => setTicker(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleResearch()}
            placeholder={t('home.researchPlaceholder')}
            style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontFamily: 'Inter, sans-serif', fontSize: 14, color: '#fafaf9' }}
          />
          <div style={{ width: 1, height: 22, background: '#292524', flexShrink: 0 }} />
          <div style={{ display: 'flex', gap: 6 }}>
            {recentTickers.slice(0, 3).map((t: string) => (
              <button
                key={t}
                onClick={() => { setTicker(t); navigate(`/research?ticker=${t}`) }}
                style={{ padding: '4px 10px', borderRadius: 999, fontSize: 12, fontWeight: 500, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', cursor: 'pointer' }}
              >
                {t}
              </button>
            ))}
          </div>
          <button
            onClick={handleResearch}
            style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 18px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}
          >
            <Icon name="play_arrow" size={16} />
            {t('home.research')}
          </button>
        </div>

        {/* SUMMARY STRIP */}
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : '2fr 1fr 1fr 1fr', gap: isMobile ? 10 : 16, marginBottom: 24 }}>
          {/* Primary */}
          <div style={{ background: '#1c1917', border: '1px solid rgba(214,211,209,0.15)', borderRadius: 14, padding: '20px 22px', position: 'relative', overflow: 'hidden' }}>
            <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 8 }}>{t('home.totalPortfolioValue')}</div>
            {isLoading ? <Skeleton h={44} /> : (
              <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 38, fontWeight: 300, letterSpacing: '-0.03em', lineHeight: 1.1 }}>
                {totals.total_value != null ? fmt(totals.total_value) : '$0'}
              </div>
            )}
            {!isLoading && totals.day_change != null && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 12.5, color: totals.day_change >= 0 ? '#22c55e' : '#ef4444' }}>
                <Icon name={totals.day_change >= 0 ? 'trending_up' : 'trending_down'} size={15} />
                {totals.day_change >= 0 ? '+' : ''}{fmt(totals.day_change)} ({totals.day_change_pct >= 0 ? '+' : ''}{totals.day_change_pct?.toFixed(2)}%) {t('home.today')}
              </div>
            )}
            <div style={{ position: 'absolute', bottom: 0, right: 0, width: 120, height: 60, opacity: 0.35 }}>
              <Sparkline gain />
            </div>
          </div>
          {/* Unrealized P&L */}
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: '20px 22px' }}>
            <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 8 }}>{t('home.unrealizedPnl')}</div>
            {isLoading ? <Skeleton h={32} /> : (
              <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 32, fontWeight: 300, letterSpacing: '-0.03em', lineHeight: 1.1, color: (totals.total_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                {totals.total_pnl != null ? fmt(totals.total_pnl) : '$0'}
              </div>
            )}
            {!isLoading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 12.5, color: (totals.total_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                <Icon name={(totals.total_pnl ?? 0) >= 0 ? 'arrow_upward' : 'arrow_downward'} size={15} />
                {t('home.allTimeReturn')}
              </div>
            )}
          </div>
          {/* Day's / Week's Change */}
          {(() => {
            const dayVal = totals.day_change ?? 0
            const dayPct = totals.day_change_pct ?? 0
            const displayVal = changeMode === 'W' ? dayVal * 5 : dayVal
            const displayPct = changeMode === 'W' ? dayPct * 5 : dayPct
            const changeColor = displayVal >= 0 ? '#22c55e' : '#ef4444'
            return (
              <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: '20px 22px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e' }}>
                    {changeMode === 'D' ? t('home.daysChange') : t('home.weeksChange')}
                  </div>
                  <div style={{ display: 'flex', gap: 2, background: '#292524', borderRadius: 6, padding: 2 }}>
                    {(['D', 'W'] as const).map(m => (
                      <button key={m} onClick={() => setChangeMode(m)}
                        style={{ padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 600, border: 'none', cursor: 'pointer',
                          background: changeMode === m ? '#d6d3d1' : 'transparent',
                          color: changeMode === m ? '#0c0a09' : '#78716c' }}>
                        {m}
                      </button>
                    ))}
                  </div>
                </div>
                {isLoading ? <Skeleton h={32} /> : (
                  <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 32, fontWeight: 300, letterSpacing: '-0.03em', lineHeight: 1.1, color: '#fafaf9' }}>
                    {displayVal !== 0 ? `${displayVal >= 0 ? '+' : ''}${fmt(displayVal)}` : '-'}
                  </div>
                )}
                {!isLoading && displayVal !== 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 12.5, color: changeColor }}>
                    <Icon name={displayVal >= 0 ? 'arrow_upward' : 'arrow_downward'} size={15} />
                    {displayPct >= 0 ? '+' : ''}{displayPct.toFixed(2)}% {changeMode === 'D' ? t('home.today') : t('home.thisWeek')}
                  </div>
                )}
              </div>
            )
          })()}
          {/* Active Alerts */}
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: '20px 22px' }}>
            <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 8 }}>{t('home.activeAlerts')}</div>
            {isLoading ? <Skeleton h={32} /> : (
              <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 32, fontWeight: 300, letterSpacing: '-0.03em', lineHeight: 1.1, color: '#fafaf9' }}>
                {alertsCount ?? 0}
              </div>
            )}
            {!isLoading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 12.5, color: '#f59e0b' }}>
                <Icon name="warning" size={15} />
                {t('home.priceAlertsWatching')}
              </div>
            )}
          </div>
        </div>

        {/* MAIN GRID */}
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 340px', gap: 20, alignItems: 'start' }}>

          {/* LEFT */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Holdings table */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #292524' }}>
                <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Icon name="pie_chart" size={16} />
                  {t('home.holdings')}
                </div>
                <Link to="/portfolio" style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                  {t('home.viewAll')} <Icon name="chevron_right" size={14} />
                </Link>
              </div>
              <div style={{ padding: '20px 20px 8px' }}>
                {isLoading ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {[1, 2, 3].map(i => <Skeleton key={i} h={40} />)}
                  </div>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr>
                        {[
                          { key: 'home.holding', isFirst: true },
                          { key: 'home.shares', isFirst: false },
                          { key: 'home.avgCost', isFirst: false },
                          { key: 'home.marketValue', isFirst: false },
                          { key: 'home.pnl', isFirst: false },
                          { key: 'home.return', isFirst: false },
                        ].map(({ key, isFirst }) => (
                          <th key={key} style={{ fontSize: 10.5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', textAlign: isFirst ? 'start' : 'end', paddingBottom: 12, borderBottom: '1px solid #292524' }}>{t(key)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(holdings.length > 0 ? holdings : []).map((h: any) => {
                        // API fields: symbol, portfolio_name, quantity, average_cost, market_value, unrealized_gain, unrealized_gain_pct
                        const pnl = h.unrealized_gain ?? h.pnl ?? 0
                        const pnlPct = h.unrealized_gain_pct ?? h.pnl_pct ?? 0
                        const shares = h.quantity ?? h.shares ?? 0
                        const avgCost = h.average_cost ?? h.avg_cost ?? 0
                        const mv = h.market_value ?? 0
                        return (
                        <tr key={`${h.symbol}-${h.portfolio_name}`}>
                          <td style={{ padding: '14px 0', borderBottom: '1px solid rgba(41,37,36,0.5)', fontSize: 13.5 }}>
                            <Link to={`/ticker/${h.symbol}`} style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
                              <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#d6d3d1', flexShrink: 0 }} />
                              <div>
                                <div style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9' }}>{h.symbol}</div>
                                <div style={{ fontSize: 11.5, color: '#a8a29e' }}>{h.portfolio_name || ''}</div>
                              </div>
                            </Link>
                          </td>
                          {[shares, avgCost ? fmt(avgCost) : '-', mv ? fmt(mv) : '-'].map((v, i) => (
                            <td key={i} style={{ padding: '14px 0', borderBottom: '1px solid rgba(41,37,36,0.5)', fontSize: 13.5, textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{v}</td>
                          ))}
                          <td style={{ padding: '14px 0', borderBottom: '1px solid rgba(41,37,36,0.5)', fontSize: 13.5, textAlign: 'end', fontVariantNumeric: 'tabular-nums', color: pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                            {pnl >= 0 ? '+' : ''}{fmt(pnl)}
                          </td>
                          <td style={{ padding: '14px 0', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end' }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 12, fontWeight: 500, padding: '3px 8px', borderRadius: 999, background: pnlPct >= 0 ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)', color: pnlPct >= 0 ? '#22c55e' : '#ef4444', border: `1px solid ${pnlPct >= 0 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}` }}>
                              {pnlPct >= 0 ? '+' : ''}{typeof pnlPct === 'number' ? pnlPct.toFixed(1) : pnlPct}%
                            </span>
                          </td>
                        </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Recent Research */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #292524' }}>
                <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Icon name="description" size={16} />
                  {t('home.recentResearch')}
                </div>
                <Link to="/reports" style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                  {t('home.allReports')} <Icon name="chevron_right" size={14} />
                </Link>
              </div>
              <div style={{ padding: 20 }}>
                {recentReports.length === 0 && !isLoading ? (
                  <div style={{ padding: '24px 0', textAlign: 'center', color: '#a8a29e', fontSize: 13 }}>{t('home.noReportsYet')}</div>
                ) : recentReports.map((r: any) => {
                  // API fields: report_id, ticker, trade_type, created_at (ISO string)
                  const reportId = r.report_id || r.id
                  const symbol = r.ticker || r.symbol || '?'
                  const title = r.title || `${symbol} research report`
                  const type = r.trade_type || r.type || ''
                  const createdAt = r.created_at ? new Date(r.created_at).toLocaleDateString() : ''
                  return (
                  <Link key={reportId} to={`/report/${reportId}`} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0', borderBottom: '1px solid rgba(41,37,36,0.5)', cursor: 'pointer', textDecoration: 'none' }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Icon name="description" size={17} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9' }}>{symbol}</div>
                      <div style={{ fontSize: 12, color: '#a8a29e', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</div>
                    </div>
                    <div style={{ textAlign: 'end', flexShrink: 0 }}>
                      <div style={{ fontSize: 11, color: '#a8a29e' }}>{type}</div>
                      <div style={{ fontSize: 11, color: '#a8a29e' }}>{createdAt}</div>
                    </div>
                  </Link>
                  )
                })}
              </div>
            </div>
          </div>

          {/* RIGHT */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Watchlist */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #292524' }}>
                <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Icon name="visibility" size={16} />
                  {t('home.watchlist')}
                </div>
                <Link to="/watchlist" style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                  {t('home.viewAll')} <Icon name="chevron_right" size={14} />
                </Link>
              </div>
              <div style={{ padding: '4px 20px' }}>
                {watchlist.length === 0 && !isLoading ? (
                  <div style={{ padding: '16px 0', textAlign: 'center', color: '#a8a29e', fontSize: 12 }}>{t('home.pinToWatchlist')}</div>
                ) : null}
                {(watchlist as any[]).map((w: any) => (
                  <Link key={w.symbol} to={`/ticker/${w.symbol}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 0', borderBottom: '1px solid rgba(41,37,36,0.5)', cursor: 'pointer', textDecoration: 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ width: 32, height: 32, borderRadius: 8, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: '#d6d3d1', fontFamily: 'Nunito, sans-serif', letterSpacing: '-0.02em' }}>
                        {w.symbol.slice(0, 2)}
                      </div>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9' }}>{w.symbol}</div>
                        <div style={{ fontSize: 11, color: '#a8a29e' }}>{w.name}</div>
                      </div>
                    </div>
                    <div style={{ textAlign: 'end' }}>
                      <div style={{ fontSize: 13, fontVariantNumeric: 'tabular-nums', color: '#fafaf9' }}>{fmt(w.price)}</div>
                      <div style={{ fontSize: 11.5, fontVariantNumeric: 'tabular-nums', color: w.change_pct >= 0 ? '#22c55e' : '#ef4444' }}>
                        {w.change_pct >= 0 ? '+' : ''}{w.change_pct}%
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>

            {/* Alerts */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #292524' }}>
                <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Icon name="notifications" size={16} />
                  {t('home.activeAlertsSection')}
                </div>
                <Link to="/alerts" style={{ fontSize: 12, color: '#a8a29e', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                  {t('home.manage')} <Icon name="chevron_right" size={14} />
                </Link>
              </div>
              <div style={{ padding: '4px 20px' }}>
                <div style={{ padding: '16px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: alertsCount != null && alertsCount > 0 ? '#22c55e' : '#a8a29e', flexShrink: 0, boxShadow: alertsCount != null && alertsCount > 0 ? '0 0 6px #22c55e' : 'none' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12.5, color: '#fafaf9' }}>
                        {alertsCount == null ? t('home.loading') : alertsCount === 0 ? t('home.noActiveAlerts') : t('home.activeAlertCount_other', { count: alertsCount })}
                      </div>
                      <div style={{ fontSize: 11, color: '#a8a29e' }}>{t('home.goToAlerts')}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* News */}
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #292524' }}>
                <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Icon name="newspaper" size={16} />
                  {t('home.marketNews')}
                </div>
              </div>
              <div style={{ padding: '4px 20px' }}>
                {(news.length > 0 ? news : []).map((n: any, i: number) => {
                  const source = n.publisher || n.source || 'News'
                  const title = n.title || ''
                  const url = n.url || '#'
                  // Simple client-side sentiment heuristic
                  const lc = title.toLowerCase()
                  const bullWords = ['beats', 'surge', 'surges', 'gain', 'gains', 'growth', 'up', 'rise', 'rises', 'rally', 'record', 'boost', 'profit', 'bullish', 'strong']
                  const bearWords = ['misses', 'crash', 'crashes', 'decline', 'declines', 'down', 'fall', 'falls', 'drop', 'loss', 'losses', 'bearish', 'weak', 'cut', 'layoff', 'disappoints', 'slump']
                  const bulls = bullWords.filter(w => lc.includes(w)).length
                  const bears = bearWords.filter(w => lc.includes(w)).length
                  const sentiment = bulls > bears ? 'bull' : bears > bulls ? 'bear' : 'neutral'
                  return (
                    <a key={i} href={url} target="_blank" rel="noopener noreferrer" style={{ display: 'block', padding: '12px 0', borderBottom: i < (news.length - 1) ? '1px solid rgba(41,37,36,0.5)' : 'none', textDecoration: 'none' }}>
                      <div style={{ fontSize: 11, color: '#a8a29e', marginBottom: 4 }}>{source}</div>
                      <div style={{ fontSize: 13, lineHeight: 1.45, color: 'rgba(250,250,249,0.75)' }}>{title}</div>
                      <div style={{ fontSize: 10.5, fontWeight: 500, marginTop: 6, color: sentiment === 'bull' ? '#22c55e' : sentiment === 'bear' ? '#ef4444' : '#a8a29e' }}>
                        {sentiment === 'bull' ? t('home.bullish') : sentiment === 'bear' ? t('home.bearish') : t('home.neutral')}
                      </div>
                    </a>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
