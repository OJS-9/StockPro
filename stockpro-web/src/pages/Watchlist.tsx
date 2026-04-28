import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import toast from 'react-hot-toast'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import Skeleton from '../components/Skeleton'
import { useApiClient } from '../api/client'
import { useLanguage } from '../LanguageContext'
import { useBreakpoint } from '../hooks/useBreakpoint'

function fmtPrice(n: number | null | undefined, _locale: string) {
  return n != null ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n) : '—'
}

function ItemMenu({ item, watchlistId: _watchlistId, onClose }: { item: any; watchlistId: string; onClose: () => void }) {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  const removeMutation = useMutation({
    mutationFn: () => api.delete(`/api/watchlist/item/${item.item_id}`).then(r => { if (!r.ok) throw new Error() }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['watchlists'] }); toast.success(t('watchlist.toasts.removed', { symbol: item.symbol })); onClose() },
    onError: () => toast.error(t('watchlist.toasts.removeFailed')),
  })

  const pinMutation = useMutation({
    mutationFn: () => api.patch(`/api/watchlist/item/${item.item_id}/pin`, {}).then(r => { if (!r.ok) throw new Error() }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['watchlists'] }); onClose() },
    onError: () => toast.error(t('watchlist.toasts.updateFailed')),
  })

  return (
    <div style={{ position: 'absolute', insetInlineEnd: 0, top: 36, zIndex: 50, background: '#1c1917', border: '1px solid #292524', borderRadius: 10, overflow: 'hidden', minWidth: 180, boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>
      <button
        onClick={() => pinMutation.mutate()}
        style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '10px 14px', background: 'transparent', border: 'none', color: item.is_pinned ? '#22c55e' : '#fafaf9', fontSize: 13, cursor: 'pointer', textAlign: 'start' }}
      >
        <Icon name={item.is_pinned ? 'push_pin' : 'push_pin'} size={15} />
        {item.is_pinned ? t('watchlist.removeFromHome') : t('watchlist.pinToHome')}
      </button>
      <div style={{ height: 1, background: '#292524' }} />
      <button
        onClick={() => removeMutation.mutate()}
        style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '10px 14px', background: 'transparent', border: 'none', color: '#ef4444', fontSize: 13, cursor: 'pointer', textAlign: 'start' }}
      >
        <Icon name="delete" size={15} />
        {t('watchlist.removeFromWatchlist')}
      </button>
    </div>
  )
}

function AddSymbolRow({ watchlistId, onDone }: { watchlistId: string; onDone: () => void }) {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const [symbol, setSymbol] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const addMutation = useMutation({
    mutationFn: () => api.post(`/api/watchlist/${watchlistId}/symbol`, { symbol: symbol.toUpperCase() }).then(r => { if (!r.ok) throw new Error() }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['watchlists'] }); toast.success(t('watchlist.toasts.added', { symbol: symbol.toUpperCase() })); onDone() },
    onError: () => toast.error(t('watchlist.toasts.addFailed')),
  })

  const submit = () => { if (symbol.trim()) addMutation.mutate() }

  return (
    <tr>
      <td colSpan={4} style={{ padding: '10px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            ref={inputRef}
            value={symbol}
            onChange={e => setSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onDone() }}
            placeholder={t('watchlist.tickerPlaceholder')}
            style={{ flex: 1, background: '#232120', border: '1px solid #292524', borderRadius: 8, padding: '7px 12px', color: '#fafaf9', fontFamily: 'Inter, Heebo, sans-serif', fontSize: 13, outline: 'none' }}
          />
          <button
            onClick={submit}
            disabled={!symbol.trim() || addMutation.isPending}
            style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: symbol.trim() ? '#d6d3d1' : '#292524', color: symbol.trim() ? '#0c0a09' : '#a8a29e', fontSize: 13, fontWeight: 600, cursor: symbol.trim() ? 'pointer' : 'not-allowed' }}
          >
            {addMutation.isPending ? t('watchlist.adding') : t('watchlist.addBtn')}
          </button>
          <button onClick={onDone} style={{ padding: '7px 12px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 13, cursor: 'pointer' }}>{t('alerts.cancel')}</button>
        </div>
      </td>
    </tr>
  )
}

export default function Watchlist() {
  const api = useApiClient()
  const { t } = useTranslation()
  const { lang } = useLanguage()
  const { isMobile } = useBreakpoint()
  const locale = lang === 'he' ? 'he-IL' : 'en-US'
  const [addingTo, setAddingTo] = useState<string | null>(null)
  const [openMenu, setOpenMenu] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['watchlists'],
    queryFn: async () => {
      const res = await api.get('/api/watchlists')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // Close menu when clicking outside
  useEffect(() => {
    const handler = () => setOpenMenu(null)
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [])

  const rawWatchlists = data?.watchlists || []
  const activeWatchlist = data?.active_watchlist

  const watchlists = rawWatchlists.map((wl: any) => {
    const wlId = wl.watchlist_id || wl.id
    const isActive = activeWatchlist && (activeWatchlist.watchlist_id === wlId || activeWatchlist.id === wlId)
    const items = isActive && activeWatchlist?.items
      ? activeWatchlist.items.map((item: any) => ({
          item_id: item.item_id,
          symbol: item.symbol,
          name: item.display_name || item.name || item.symbol,
          price: item.price != null ? Number(item.price) : null,
          change_pct: item.change_pct != null ? Number(item.change_pct) : null,
          is_pinned: Boolean(item.is_pinned),
        }))
      : []
    return { id: wlId, name: wl.name, items }
  })

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1200, margin: '0 auto', padding: isMobile ? '20px 16px 60px' : '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32 }}>
          <div>
            <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>{t('watchlist.watchlists')}</div>
            <div style={{ fontSize: 13, color: '#a8a29e' }}>{watchlists.length} list{watchlists.length !== 1 ? 's' : ''} &nbsp;&middot;&nbsp; {t('watchlist.updatedJustNow')}</div>
          </div>
        </div>

        {isLoading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[1, 2].map(i => (
              <div key={i} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: 20 }}>
                <Skeleton height={20} width={140} />
                <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {[1, 2, 3].map(j => <Skeleton key={j} height={44} />)}
                </div>
              </div>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {watchlists.map((wl: any) => (
            <div key={wl.id} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #292524' }}>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600 }}>{wl.name}</div>
                  <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 2 }}>{wl.items?.length || 0} {t('watchlist.symbols')}</div>
                </div>
                <button
                  onClick={() => setAddingTo(addingTo === wl.id ? null : wl.id)}
                  style={{ padding: '6px 14px', borderRadius: 7, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}
                >
                  <Icon name="add" size={14} /> {t('watchlist.addSymbol')}
                </button>
              </div>
              <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: isMobile ? 560 : undefined }}>
                <thead>
                  <tr>
                    {[t('watchlist.symbol'), t('watchlist.price'), t('watchlist.change'), t('watchlist.home'), ''].map(h => (
                      <th key={h} style={{ fontSize: 10.5, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', textAlign: h === t('watchlist.symbol') ? 'start' : 'end', padding: '10px 20px', borderBottom: '1px solid #292524' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {addingTo === wl.id && (
                    <AddSymbolRow watchlistId={wl.id} onDone={() => setAddingTo(null)} />
                  )}
                  {(wl.items || []).map((item: any) => (
                    <tr key={item.symbol}>
                      <td style={{ padding: '14px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)' }}>
                        <Link to={`/ticker/${item.symbol}`} style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
                          <div style={{ width: 32, height: 32, borderRadius: 8, background: '#232120', border: '1px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: '#d6d3d1', fontFamily: 'Nunito, "Secular One", Heebo, sans-serif' }}>
                            {item.symbol.slice(0, 2)}
                          </div>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9' }}>{item.symbol}</div>
                            <div style={{ fontSize: 11.5, color: '#a8a29e' }}>{item.name}</div>
                          </div>
                        </Link>
                      </td>
                      <td style={{ padding: '14px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end', fontVariantNumeric: 'tabular-nums', fontSize: 13.5, color: '#fafaf9' }}>
                        {item.price != null ? fmtPrice(item.price, locale) : '—'}
                      </td>
                      <td style={{ padding: '14px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end' }}>
                        {item.change_pct != null ? (
                          <span style={{ fontSize: 12.5, fontWeight: 500, padding: '3px 8px', borderRadius: 999, background: item.change_pct >= 0 ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)', color: item.change_pct >= 0 ? '#22c55e' : '#ef4444', border: `1px solid ${item.change_pct >= 0 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`, fontVariantNumeric: 'tabular-nums' }}>
                            <bdi>{item.change_pct >= 0 ? '+' : ''}{item.change_pct?.toFixed(2)}%</bdi>
                          </span>
                        ) : <span style={{ color: '#a8a29e', fontSize: 12 }}>—</span>}
                      </td>
                      <td style={{ padding: '14px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end' }}>
                        {item.is_pinned ? (
                          <span style={{ fontSize: 11, color: '#22c55e', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Icon name="push_pin" size={13} /> {t('watchlist.pinned')}
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, color: '#a8a29e' }}>—</span>
                        )}
                      </td>
                      <td style={{ padding: '14px 20px', borderBottom: '1px solid rgba(41,37,36,0.5)', textAlign: 'end' }}>
                        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', alignItems: 'center' }}>
                          <Link to={`/research?ticker=${item.symbol}`} style={{ width: 28, height: 28, borderRadius: 7, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', display: 'flex', alignItems: 'center', justifyContent: 'center', textDecoration: 'none' }} title={t('watchlist.research')}>
                            <Icon name="query_stats" size={15} />
                          </Link>
                          <div style={{ position: 'relative' }}>
                            <button
                              onClick={e => { e.stopPropagation(); setOpenMenu(openMenu === item.item_id ? null : item.item_id) }}
                              style={{ width: 28, height: 28, borderRadius: 7, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                            >
                              <Icon name="more_vert" size={16} />
                            </button>
                            {openMenu === item.item_id && (
                              <ItemMenu item={item} watchlistId={wl.id} onClose={() => setOpenMenu(null)} />
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {(!wl.items || wl.items.length === 0) && addingTo !== wl.id && (
                    <tr>
                      <td colSpan={5} style={{ padding: '24px 20px', textAlign: 'center', color: '#a8a29e', fontSize: 13 }}>
                        {t('watchlist.noSymbols')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}
