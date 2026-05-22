import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../api/client'
import Icon from '../../components/Icon'

function formatDate(iso: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function KpiCard({ icon, label, value }: { icon: string; label: string; value: string | number }) {
  return (
    <div style={{
      background: '#1c1917', border: '1px solid #292524', borderRadius: 16,
      padding: '24px 28px', flex: '1 1 0', minWidth: 180,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <Icon name={icon} size={20} style={{ color: '#78716c' }} />
        <span style={{ fontSize: 13, color: '#a8a29e', fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, fontFamily: "'Nunito', sans-serif", color: '#fafaf9' }}>
        {value}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const api = useApiClient()
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-dashboard'],
    queryFn: async () => {
      const res = await api.get('/api/admin/dashboard')
      if (!res.ok) throw new Error('Failed to load dashboard')
      return res.json()
    },
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin-dashboard'] })

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <h1 style={{ fontFamily: "'Nunito', sans-serif", fontWeight: 700, fontSize: 24, color: '#fafaf9', margin: 0 }}>
          Dashboard
        </h1>
        <button
          onClick={refresh}
          style={{
            background: '#292524', border: '1px solid #292524', borderRadius: 10,
            padding: '8px 16px', color: '#d6d3d1', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 500,
          }}
        >
          <Icon name="refresh" size={16} />
          Refresh
        </button>
      </div>

      {/* KPI Cards */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 32, flexWrap: 'wrap' }}>
        <KpiCard icon="group" label="Total Users" value={isLoading ? '-' : data?.total_users ?? 0} />
        <KpiCard icon="description" label="Reports Today" value={isLoading ? '-' : data?.reports_today ?? 0} />
        <KpiCard icon="payments" label="Revenue (MTD)" value="$0" />
      </div>

      {/* Recent lists side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Recent Signups */}
        <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, color: '#d6d3d1', margin: '0 0 16px' }}>
            Recent Signups
          </h2>
          {isLoading ? (
            <div style={{ color: '#78716c', fontSize: 13 }}>Loading...</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #292524' }}>
                  <th style={thStyle}>Name</th>
                  <th style={thStyle}>Email</th>
                  <th style={thStyle}>Date</th>
                </tr>
              </thead>
              <tbody>
                {(data?.recent_signups ?? []).map((u: any) => (
                  <tr key={u.user_id} style={{ borderBottom: '1px solid #1a1816' }}>
                    <td style={tdStyle}>{u.username}</td>
                    <td style={{ ...tdStyle, color: '#a8a29e' }}>{u.email}</td>
                    <td style={{ ...tdStyle, color: '#78716c' }}>{formatDate(u.created_at)}</td>
                  </tr>
                ))}
                {(data?.recent_signups ?? []).length === 0 && (
                  <tr><td colSpan={3} style={{ ...tdStyle, color: '#78716c' }}>No users yet</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Recent Reports */}
        <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, color: '#d6d3d1', margin: '0 0 16px' }}>
            Recent Reports
          </h2>
          {isLoading ? (
            <div style={{ color: '#78716c', fontSize: 13 }}>Loading...</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #292524' }}>
                  <th style={thStyle}>Ticker</th>
                  <th style={thStyle}>User</th>
                  <th style={thStyle}>Date</th>
                </tr>
              </thead>
              <tbody>
                {(data?.recent_reports ?? []).map((r: any) => (
                  <tr key={r.report_id} style={{ borderBottom: '1px solid #1a1816' }}>
                    <td style={{ ...tdStyle, fontWeight: 600, color: '#fafaf9' }}>{r.ticker}</td>
                    <td style={{ ...tdStyle, color: '#a8a29e' }}>{r.username || '-'}</td>
                    <td style={{ ...tdStyle, color: '#78716c' }}>{formatDate(r.created_at)}</td>
                  </tr>
                ))}
                {(data?.recent_reports ?? []).length === 0 && (
                  <tr><td colSpan={3} style={{ ...tdStyle, color: '#78716c' }}>No reports yet</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = {
  textAlign: 'left', padding: '8px 10px', fontSize: 12, fontWeight: 600,
  color: '#78716c', textTransform: 'uppercase', letterSpacing: '0.04em',
}

const tdStyle: React.CSSProperties = {
  padding: '10px 10px', fontSize: 13, color: '#d6d3d1',
}
