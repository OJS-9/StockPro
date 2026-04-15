import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../api/client'
import Icon from '../../components/Icon'

function FeatureCard({ icon, label, value }: { icon: string; label: string; value: number | string }) {
  return (
    <div style={{
      background: '#1c1917', border: '1px solid #292524', borderRadius: 14,
      padding: '20px 24px', flex: '1 1 0', minWidth: 140,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Icon name={icon} size={18} style={{ color: '#78716c' }} />
        <span style={{ fontSize: 12, color: '#a8a29e', fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "'Nunito', sans-serif", color: '#fafaf9' }}>
        {value}
      </div>
    </div>
  )
}

function MiniChart({ data, label }: { data: { day: string; count: number }[]; label: string }) {
  if (!data || data.length === 0) {
    return (
      <div style={{ color: '#78716c', fontSize: 13, padding: 16 }}>No data yet</div>
    )
  }
  const max = Math.max(...data.map(d => d.count), 1)
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#d6d3d1', marginBottom: 12 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 100 }}>
        {data.map((d) => (
          <div
            key={d.day}
            title={`${d.day}: ${d.count}`}
            style={{
              flex: '1 1 0',
              background: '#292524',
              borderRadius: '4px 4px 0 0',
              height: `${Math.max((d.count / max) * 100, 4)}%`,
              minWidth: 4,
              transition: 'height 0.3s',
              cursor: 'default',
            }}
          />
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
        <span style={{ fontSize: 10, color: '#57534e' }}>{data[0]?.day?.slice(5)}</span>
        <span style={{ fontSize: 10, color: '#57534e' }}>{data[data.length - 1]?.day?.slice(5)}</span>
      </div>
    </div>
  )
}

export default function Stats() {
  const api = useApiClient()
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: async () => {
      const res = await api.get('/api/admin/stats')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin-stats'] })

  const usage = data?.feature_usage ?? {}
  const agentPerf = data?.agent_performance ?? {}

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h1 style={{ fontFamily: "'Nunito', sans-serif", fontWeight: 700, fontSize: 24, color: '#fafaf9', margin: 0 }}>
          Stats
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

      {isLoading ? (
        <div style={{ color: '#78716c', fontSize: 13 }}>Loading...</div>
      ) : (
        <>
          {/* Charts */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 28 }}>
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: 24 }}>
              <MiniChart data={data?.reports_per_day ?? []} label="Reports (Last 30 Days)" />
            </div>
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: 24 }}>
              <MiniChart data={data?.signups_per_day ?? []} label="Signups (Last 30 Days)" />
            </div>
          </div>

          {/* Feature usage */}
          <div style={{ marginBottom: 28 }}>
            <h2 style={{ fontSize: 15, fontWeight: 600, color: '#d6d3d1', marginBottom: 14 }}>Feature Usage</h2>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <FeatureCard icon="pie_chart" label="Portfolios" value={usage.portfolios ?? 0} />
              <FeatureCard icon="visibility" label="Watchlists" value={usage.watchlists ?? 0} />
              <FeatureCard icon="notifications" label="Alerts" value={usage.alerts ?? 0} />
              <FeatureCard icon="description" label="Reports" value={usage.reports ?? 0} />
            </div>
          </div>

          {/* Agent performance */}
          <div>
            <h2 style={{ fontSize: 15, fontWeight: 600, color: '#d6d3d1', marginBottom: 14 }}>Agent Performance</h2>
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: 24 }}>
              {agentPerf.total_runs === 0 ? (
                <div style={{ color: '#78716c', fontSize: 13 }}>No research runs logged yet</div>
              ) : (
                <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
                  <Stat label="Total Runs" value={agentPerf.total_runs ?? 0} />
                  <Stat label="Successes" value={agentPerf.successes ?? 0} color="#22c55e" />
                  <Stat label="Errors" value={agentPerf.errors ?? 0} color="#ef4444" />
                  <Stat
                    label="Avg Duration"
                    value={agentPerf.avg_duration_s != null ? `${agentPerf.avg_duration_s.toFixed(1)}s` : '-'}
                  />
                  <Stat
                    label="Success Rate"
                    value={
                      agentPerf.total_runs > 0
                        ? `${((agentPerf.successes / agentPerf.total_runs) * 100).toFixed(0)}%`
                        : '-'
                    }
                  />
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: '#78716c', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "'Nunito', sans-serif", color: color ?? '#fafaf9' }}>
        {value}
      </div>
    </div>
  )
}
