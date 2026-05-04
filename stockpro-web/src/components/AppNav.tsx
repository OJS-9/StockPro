import { useState, useRef, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useUser, useClerk } from '@clerk/clerk-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import Icon from './Icon'
import { useApiClient } from '../api/client'
import { useBreakpoint } from '../hooks/useBreakpoint'
import { useResearchProgress } from '../ResearchProgressContext'
import { useLanguage } from '../LanguageContext'

const navLinks = [
  { to: '/home', icon: 'dashboard', tKey: 'nav.dashboard' },
  { to: '/portfolio', icon: 'pie_chart', tKey: 'nav.portfolio' },
  { to: '/watchlist', icon: 'visibility', tKey: 'nav.watchlist' },
  { to: '/reports', icon: 'description', tKey: 'nav.reports' },
  { to: '/alerts', icon: 'notifications', tKey: 'nav.alerts' },
]

function timeAgo(iso: string, locale: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return rtf.format(0, 'minute')
  if (mins < 60) return rtf.format(-mins, 'minute')
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return rtf.format(-hrs, 'hour')
  return rtf.format(-Math.floor(hrs / 24), 'day')
}

export default function AppNav() {
  const location = useLocation()
  const { user } = useUser()
  const { signOut } = useClerk()
  const api = useApiClient()
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const { lang } = useLanguage()
  const locale = lang === 'he' ? 'he-IL' : 'en-US'
  const [showPanel, setShowPanel] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const bellRef = useRef<HTMLButtonElement>(null)
  const { isMobile } = useBreakpoint()
  const navigate = useNavigate()
  const research = useResearchProgress()

  // Read notification data from shared query (NotificationListener in App.tsx handles toasts)
  // Provides its own queryFn so it works even if it renders before NotificationListener
  const { data } = useQuery<{ notifications: any[]; unread_count: number }>({
    queryKey: ['alert-notifications'],
    queryFn: async () => {
      const res = await api.get('/api/alerts/notifications?limit=20')
      if (!res.ok) return { notifications: [], unread_count: 0 }
      return res.json()
    },
    staleTime: 30_000,
  })

  const notifications: any[] = (data?.notifications ?? []).filter((n: any) => !n.read_at)
  const unreadCount: number = data?.unread_count ?? 0

  // Close panel on click outside
  useEffect(() => {
    if (!showPanel) return
    const handler = (e: MouseEvent) => {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        bellRef.current && !bellRef.current.contains(e.target as Node)
      ) {
        setShowPanel(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showPanel])

  const dismissOne = (notifId: string) => {
    // Optimistically remove from list
    queryClient.setQueryData(['alert-notifications'], (old: any) => {
      if (!old) return old
      const remaining = old.notifications.filter((n: any) => n.notification_id !== notifId)
      const wasUnread = old.notifications.find((n: any) => n.notification_id === notifId && !n.read_at)
      return {
        notifications: remaining,
        unread_count: wasUnread ? Math.max(0, (old.unread_count ?? 0) - 1) : old.unread_count,
      }
    })
    api.patch(`/api/alerts/notifications/${notifId}`, { read: true }).then(() => {
      queryClient.invalidateQueries({ queryKey: ['alert-notifications'] })
    })
  }

  const clearAll = () => {
    // Optimistically clear list
    queryClient.setQueryData(['alert-notifications'], () => ({
      notifications: [],
      unread_count: 0,
    }))
    api.post('/api/alerts/notifications/mark-all-read', {}).then(() => {
      queryClient.invalidateQueries({ queryKey: ['alert-notifications'] })
    })
  }

  const initials = user
    ? ((user.firstName?.[0] ?? '') + (user.lastName?.[0] ?? '')).toUpperCase() || user.emailAddresses[0]?.emailAddress?.[0]?.toUpperCase() || 'U'
    : 'U'

  const isActive = (to: string) => {
    if (to === '/home') return location.pathname === '/home'
    return location.pathname.startsWith(to)
  }

  const showProgressStrip = research.status === 'generating' || research.status === 'ready' || research.status === 'error'

  return (
    <div style={{ position: 'sticky', top: 0, zIndex: 100 }}>
    <nav
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: isMobile ? '0 16px' : '0 48px',
        height: 60,
        background: 'rgba(12,10,9,0.95)',
        backdropFilter: 'blur(16px)',
        borderBottom: showProgressStrip ? 'none' : '1px solid #292524',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 40 }}>
        <Link
          to="/home"
          style={{
            fontFamily: 'Nunito, "Secular One", Heebo, sans-serif',
            fontSize: 17,
            fontWeight: 700,
            color: '#d6d3d1',
            letterSpacing: '-0.02em',
            textDecoration: 'none',
          }}
        >
          StockPro
        </Link>
        {isMobile ? (
          <>
            <button
              onClick={() => setMenuOpen(o => !o)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#e7e5e4', display: 'flex', alignItems: 'center', padding: 8 }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
                {menuOpen ? 'close' : 'menu'}
              </span>
            </button>
            {menuOpen && (
              <div style={{
                position: 'fixed', top: 60, insetInlineStart: 0, width: '100vw', background: 'rgba(12,10,9,0.98)',
                borderBottom: '1px solid #292524', zIndex: 200, display: 'flex', flexDirection: 'column', padding: '8px 0'
              }}>
                {navLinks.map(link => (
                  <Link
                    key={link.to}
                    to={link.to}
                    onClick={() => setMenuOpen(false)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px',
                      color: isActive(link.to) ? '#f97316' : '#e7e5e4',
                      textDecoration: 'none', fontWeight: isActive(link.to) ? 600 : 400, fontSize: 15
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 20 }}>{link.icon}</span>
                    {t(link.tKey)}
                  </Link>
                ))}
              </div>
            )}
          </>
        ) : (
          <div style={{ display: 'flex', gap: 4 }}>
            {navLinks.map(({ to, icon, tKey }) => (
              <Link
                key={to}
                to={to}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  color: isActive(to) ? '#fafaf9' : '#a8a29e',
                  textDecoration: 'none',
                  fontSize: 13.5,
                  fontWeight: 500,
                  padding: '6px 12px',
                  borderRadius: 8,
                  background: isActive(to) ? 'rgba(214,211,209,0.07)' : 'transparent',
                  transition: 'all 0.15s',
                }}
              >
                <Icon name={icon} size={18} />
                {t(tKey)}
              </Link>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <UpgradePill />
        <Link to="/research" style={{ textDecoration: 'none' }}>
          <button
            style={{
              width: 34,
              height: 34,
              borderRadius: 8,
              border: '1px solid #292524',
              background: 'transparent',
              color: '#a8a29e',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title={t('nav.newResearch')}
          >
            <Icon name="search" size={18} />
          </button>
        </Link>

        {/* Bell with notification dropdown */}
        <div style={{ position: 'relative' }}>
          <button
            ref={bellRef}
            onClick={() => setShowPanel(s => !s)}
            style={{
              position: 'relative',
              width: 34,
              height: 34,
              borderRadius: 8,
              border: '1px solid #292524',
              background: showPanel ? 'rgba(214,211,209,0.07)' : 'transparent',
              color: unreadCount > 0 ? '#fafaf9' : '#a8a29e',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Icon name="notifications" size={18} />
            {unreadCount > 0 && (
              <span style={{
                position: 'absolute',
                top: 4,
                insetInlineEnd: 4,
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: '#ef4444',
                border: '1.5px solid #0c0a09',
              }} />
            )}
          </button>

          {showPanel && (
            <div
              ref={panelRef}
              style={{
                position: 'absolute',
                top: 42,
                insetInlineEnd: 0,
                width: 340,
                maxHeight: 400,
                overflowY: 'auto',
                background: '#1c1917',
                border: '1px solid #292524',
                borderRadius: 14,
                boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                zIndex: 200,
              }}
            >
              {/* Header */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px 10px',
                borderBottom: '1px solid #292524',
              }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9' }}>{t('nav.notifications')}</span>
                {notifications.length > 0 && (
                  <button
                    onClick={clearAll}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#a8a29e',
                      fontSize: 12,
                      cursor: 'pointer',
                      padding: '2px 6px',
                      borderRadius: 4,
                    }}
                  >
                    {t('nav.clearAll')}
                  </button>
                )}
              </div>

              {/* Notification list */}
              {notifications.length === 0 ? (
                <div style={{ padding: '32px 16px', textAlign: 'center', color: '#a8a29e', fontSize: 13 }}>
                  {t('nav.noNotifications')}
                </div>
              ) : (
                notifications.map((n: any) => (
                  <div
                    key={n.notification_id}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 10,
                      padding: '12px 16px',
                      borderBottom: '1px solid rgba(41,37,36,0.5)',
                      background: n.read_at ? 'transparent' : 'rgba(214,211,209,0.03)',
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{
                          fontSize: 11,
                          fontWeight: 700,
                          fontFamily: 'Nunito, "Secular One", Heebo, sans-serif',
                          padding: '2px 8px',
                          borderRadius: 5,
                          background: '#232120',
                          border: '1px solid #292524',
                          letterSpacing: '0.02em',
                        }}>
                          {n.symbol}
                        </span>
                        <span style={{ fontSize: 11, color: '#57534e' }}>
                          {n.created_at ? timeAgo(n.created_at, locale) : ''}
                        </span>
                        {!n.read_at && (
                          <span style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: '#3b82f6',
                            flexShrink: 0,
                          }} />
                        )}
                      </div>
                      <div style={{ fontSize: 12, color: '#d6d3d1', lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {n.body}
                      </div>
                    </div>
                    <button
                      onClick={() => dismissOne(n.notification_id)}
                      style={{
                        flexShrink: 0,
                        width: 22,
                        height: 22,
                        borderRadius: 5,
                        border: 'none',
                        background: 'transparent',
                        color: '#57534e',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        marginTop: 2,
                      }}
                      title="Dismiss"
                    >
                      <Icon name="close" size={14} />
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        <button
          onClick={() => signOut({ redirectUrl: import.meta.env.BASE_URL })}
          title={t('nav.signOut')}
          style={{
            width: 34,
            height: 34,
            borderRadius: 8,
            border: '1px solid #292524',
            background: 'transparent',
            color: '#a8a29e',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="logout" size={18} />
        </button>
        <Link to="/settings" style={{ textDecoration: 'none' }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #2d2b29, #3d3a37)',
              border: '1px solid #292524',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 12,
              fontWeight: 600,
              color: '#d6d3d1',
              cursor: 'pointer',
              fontFamily: 'Nunito, "Secular One", Heebo, sans-serif',
            }}
          >
            {user?.imageUrl ? (
              <img src={user.imageUrl} alt={initials} style={{ width: 32, height: 32, borderRadius: '50%', objectFit: 'cover' }} />
            ) : (
              initials
            )}
          </div>
        </Link>
      </div>
    </nav>
    {showProgressStrip && (
      <div
        style={{
          background: 'rgba(12,10,9,0.95)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid #292524',
          padding: isMobile ? '8px 16px' : '10px 48px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, minWidth: 0 }}>
          <Icon name={research.status === 'ready' ? 'check_circle' : research.status === 'error' ? 'error' : 'auto_awesome'} size={16} />
          <span style={{ fontSize: 12.5, fontWeight: 600, color: '#fafaf9', fontFamily: 'Nunito, sans-serif', whiteSpace: 'nowrap' }}>
            {research.ticker || 'Report'}
          </span>
          {!isMobile && (() => {
            const codeKey = research.stepCode ? `research.step.${research.stepCode}` : ''
            let label = ''
            if (codeKey) {
              const translated = t(codeKey, { done: research.done ?? 0, total: research.total ?? 0 })
              if (translated !== codeKey) label = translated
            }
            if (!label) label = research.step
            return label ? (
              <span style={{ fontSize: 12, color: '#a8a29e', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 260 }}>
                · {label}
              </span>
            ) : null
          })()}
        </div>
        <div style={{ flex: 1, height: 6, background: '#292524', borderRadius: 999, overflow: 'hidden', minWidth: 60 }}>
          <div
            style={{
              height: '100%',
              width: `${research.progress}%`,
              borderRadius: 999,
              background: research.status === 'error' ? '#ef4444' : research.status === 'ready' ? '#22c55e' : '#d6d3d1',
              transition: 'width 0.4s ease',
            }}
          />
        </div>
        <span style={{ fontSize: 12, color: '#a8a29e', fontVariantNumeric: 'tabular-nums', minWidth: 36, textAlign: 'end', flexShrink: 0 }}>
          {research.progress}%
        </span>
        {research.status === 'ready' && research.reportId && (
          <button
            onClick={() => { const id = research.reportId!; research.dismiss(); navigate(`/report/${id}`) }}
            style={{
              background: '#d6d3d1',
              color: '#0c0a09',
              border: 'none',
              borderRadius: 8,
              padding: isMobile ? '6px 10px' : '6px 14px',
              fontSize: 12.5,
              fontWeight: 700,
              fontFamily: 'Nunito, sans-serif',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
          >
            <Icon name="arrow_forward" size={14} />
            {t('nav.showReport')}
          </button>
        )}
        {(research.status === 'ready' || research.status === 'error') && (
          <button
            onClick={() => research.dismiss()}
            title={t('nav.dismiss')}
            style={{
              width: 26,
              height: 26,
              borderRadius: 6,
              border: '1px solid #292524',
              background: 'transparent',
              color: '#a8a29e',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Icon name="close" size={14} />
          </button>
        )}
      </div>
    )}
    </div>
  )
}

/** Top-right upgrade pill. Shows for free + starter; hidden for ultra. */
function UpgradePill() {
  const api = useApiClient()
  const { data } = useQuery<{ profile: { tier: string } }>({
    queryKey: ['settings'],
    queryFn: async () => {
      const res = await api.get('/api/settings')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
    staleTime: 60_000,
  })
  const tier = data?.profile?.tier || 'free'
  if (tier === 'ultra') return null

  const label = tier === 'free' ? 'Upgrade' : 'Plan'
  return (
    <Link
      to="/settings?section=plan"
      style={{
        textDecoration: 'none',
        padding: '6px 14px',
        borderRadius: 100,
        background: tier === 'free' ? '#d6d3d1' : 'transparent',
        color: tier === 'free' ? '#0c0a09' : '#d6d3d1',
        border: tier === 'free' ? 'none' : '1px solid #292524',
        fontSize: 12.5,
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </Link>
  )
}
