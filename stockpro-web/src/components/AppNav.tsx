import { Link, useLocation } from 'react-router'
import { useUser, useClerk } from '@clerk/clerk-react'
import Icon from './Icon'

const navLinks = [
  { to: '/home', icon: 'dashboard', label: 'Dashboard' },
  { to: '/portfolio', icon: 'pie_chart', label: 'Portfolio' },
  { to: '/watchlist', icon: 'visibility', label: 'Watchlist' },
  { to: '/reports', icon: 'description', label: 'Reports' },
  { to: '/alerts', icon: 'notifications', label: 'Alerts' },
]

export default function AppNav() {
  const location = useLocation()
  const { user } = useUser()
  const { signOut } = useClerk()

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
        <Link to="/alerts" style={{ textDecoration: 'none' }}>
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
          >
            <Icon name="notifications" size={18} />
          </button>
        </Link>
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
