import { useState, useRef, useEffect } from 'react'
import { Link, useLocation } from 'react-router'
import { useUser, useClerk } from '@clerk/clerk-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Icon from './Icon'
import { useApiClient } from '../api/client'

const navLinks = [
  { to: '/home', icon: 'dashboard', label: 'Dashboard' },
  { to: '/portfolio', icon: 'pie_chart', label: 'Portfolio' },
  { to: '/watchlist', icon: 'visibility', label: 'Watchlist' },
  { to: '/reports', icon: 'description', label: 'Reports' },
  { to: '/alerts', icon: 'notifications', label: 'Alerts' },
]

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function AppNav() {
  const location = useLocation()
  const { user } = useUser()
  const { signOut } = useClerk()
  const api = useApiClient()
  const queryClient = useQueryClient()
  const [showPanel, setShowPanel] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const bellRef = useRef<HTMLButtonElement>(null)

  // Read notification data from shared query (NotificationListener in App.tsx handles toasts)
  const { data } = useQuery({
    queryKey: ['alert-notifications'],
    queryFn: async () => {
      const res = await api.get('/api/alerts/notifications?limit=20')
      if (!res.ok) return { notifications: [], unread_count: 0 }
      return res.json()
    },
    refetchInterval: 30_000,
    staleTime: 25_000,
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

  return (
    <nav
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 48px',
        height: 60,
        background: 'rgba(12,10,9,0.95)',
        backdropFilter: 'blur(16px)',
        borderBottom: '1px solid #292524',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 40 }}>
        <Link
          to="/home"
          style={{
            fontFamily: 'Nunito, sans-serif',
            fontSize: 17,
            fontWeight: 700,
            color: '#d6d3d1',
            letterSpacing: '-0.02em',
            textDecoration: 'none',
          }}
        >
          StockPro
        </Link>
        <div style={{ display: 'flex', gap: 4 }}>
          {navLinks.map(({ to, icon, label }) => (
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
              {label}
            </Link>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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
            title="New Research"
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
                right: 4,
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
                right: 0,
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
                <span style={{ fontSize: 13, fontWeight: 600, color: '#fafaf9' }}>Notifications</span>
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
                    Clear all
                  </button>
                )}
              </div>

              {/* Notification list */}
              {notifications.length === 0 ? (
                <div style={{ padding: '32px 16px', textAlign: 'center', color: '#a8a29e', fontSize: 13 }}>
                  No notifications
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
                          fontFamily: 'Nunito, sans-serif',
                          padding: '2px 8px',
                          borderRadius: 5,
                          background: '#232120',
                          border: '1px solid #292524',
                          letterSpacing: '0.02em',
                        }}>
                          {n.symbol}
                        </span>
                        <span style={{ fontSize: 11, color: '#57534e' }}>
                          {n.created_at ? timeAgo(n.created_at) : ''}
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
          onClick={() => signOut({ redirectUrl: '/' })}
          title="Sign out"
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
              fontFamily: 'Nunito, sans-serif',
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
  )
}
