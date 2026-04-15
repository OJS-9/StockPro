import { NavLink, Outlet, useNavigate } from 'react-router'
import Icon from '../../components/Icon'

const tabs = [
  { to: '/admin', icon: 'dashboard', label: 'Dashboard', end: true },
  { to: '/admin/users', icon: 'group', label: 'Users' },
  { to: '/admin/stats', icon: 'bar_chart', label: 'Stats' },
  { to: '/admin/logs', icon: 'receipt_long', label: 'Logs' },
  { to: '/admin/config', icon: 'settings', label: 'Config' },
]

export default function AdminLayout() {
  const navigate = useNavigate()

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0c0a09' }}>
      {/* Sidebar */}
      <aside style={{
        width: 220,
        background: '#1c1917',
        borderRight: '1px solid #292524',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 0',
        flexShrink: 0,
      }}>
        <button
          onClick={() => navigate('/home')}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            padding: '0 20px 20px', display: 'flex', alignItems: 'center', gap: 8,
            color: '#d6d3d1',
          }}
        >
          <Icon name="arrow_back" size={18} />
          <span style={{ fontFamily: "'Nunito', sans-serif", fontWeight: 700, fontSize: 18 }}>
            StockPro
          </span>
        </button>

        <div style={{ padding: '0 12px', marginBottom: 8 }}>
          <span style={{
            fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '0.05em', color: '#78716c', padding: '0 8px',
          }}>
            Admin
          </span>
        </div>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '0 12px' }}>
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px', borderRadius: 10, textDecoration: 'none',
                fontSize: 14, fontWeight: 500, transition: 'background 0.15s',
                color: isActive ? '#fafaf9' : '#a8a29e',
                background: isActive ? '#292524' : 'transparent',
              })}
            >
              <Icon name={tab.icon} size={20} />
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Content */}
      <main style={{ flex: 1, padding: '32px 40px', overflowY: 'auto', maxHeight: '100vh' }}>
        <Outlet />
      </main>
    </div>
  )
}
