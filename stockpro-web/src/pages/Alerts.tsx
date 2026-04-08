import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'

const fmt = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)

// No mock alerts — use real API data only

export default function Alerts() {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  // API create fields: symbol, direction (above|below), target_price, asset_type (stock|crypto)
  const [newAlert, setNewAlert] = useState({ symbol: '', direction: 'above', target: '', asset_type: 'stock' })

  const { data } = useQuery({
    queryKey: ['alerts'],
    queryFn: async () => {
      const res = await api.get('/api/alerts')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
    refetchInterval: 30_000,
  })

  const toggleMutation = useMutation({
    // PATCH /api/alerts/<id> with {active: bool}
    mutationFn: async ({ id, active }: { id: string; active: boolean }) => {
      const res = await api.patch(`/api/alerts/${id}`, { active })
      if (!res.ok) throw new Error('Failed')
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
    onError: () => toast.error('Failed to update alert'),
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.delete(`/api/alerts/${id}`)
      if (!res.ok) throw new Error('Failed')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      toast.success('Alert deleted')
    },
    onError: () => toast.error('Failed to delete alert'),
  })

  const createMutation = useMutation({
    // POST /api/alerts with {symbol, direction, target_price, asset_type}
    mutationFn: async () => {
      const res = await api.post('/api/alerts', {
        symbol: newAlert.symbol.toUpperCase(),
        direction: newAlert.direction,
        target_price: parseFloat(newAlert.target),
        asset_type: newAlert.asset_type,
      })
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      setNewAlert({ symbol: '', direction: 'above', target: '', asset_type: 'stock' })
      setShowCreate(false)
      toast.success('Alert created')
    },
    onError: () => toast.error('Failed to create alert'),
  })

  // API fields: alert_id, symbol, direction (above|below), target_price, active (bool), created_at
  const alerts = data?.alerts || []
  const stats = data?.stats || {}
  const activeCount = stats.active_count ?? alerts.filter((a: any) => a.active && !a.last_triggered_at).length
  const pausedCount = stats.paused_count ?? alerts.filter((a: any) => !a.active).length
  const triggeredCount = stats.triggered_count ?? alerts.filter((a: any) => !!a.last_triggered_at).length
  const triggered30d = stats.triggered_30d_count ?? 0

  const getProgress = (a: any) => {
    const target = a.target_price ?? a.target ?? 0
    const current = a.current_price ?? 0
    if (!target || !current) return 50
    if (a.direction === 'above') {
      return Math.min((current / target) * 100, 100)
    }
    return Math.min(((target - current) / target + 1) * 100, 100)
  }

  const statusDotColor = (active: boolean) => active ? '#22c55e' : '#a8a29e'

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1000, margin: '0 auto', padding: '36px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32 }}>
          <div>
            <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>Price Alerts</div>
            <div style={{ fontSize: 13, color: '#a8a29e' }}>{activeCount} active &nbsp;&middot;&nbsp; {triggeredCount} triggered &nbsp;&middot;&nbsp; {pausedCount} paused</div>
          </div>
          <button
            onClick={() => setShowCreate(s => !s)}
            style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 16px', borderRadius: 8, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Icon name="add" size={16} /> New Alert
          </button>
        </div>

        {/* STATS */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 32 }}>
          {[
            { label: 'Active', val: activeCount, color: '#22c55e' as string },
            { label: 'Triggered', val: triggeredCount, color: '#f59e0b' as string },
            { label: 'Paused', val: pausedCount, color: '#a8a29e' as string },
            { label: 'Total', val: alerts.length, color: '#fafaf9' as string },
          ].map(({ label, val, color }) => (
            <div key={label} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 12, padding: '16px 18px' }}>
              <div style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 8 }}>{label}</div>
              <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 28, fontWeight: 600, lineHeight: 1, color }}>{val}</div>
            </div>
          ))}
        </div>

        {/* CREATE FORM */}
        {showCreate && (
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: '24px', marginBottom: 24 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Create Alert</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#a8a29e', marginBottom: 6 }}>Ticker</label>
                <input value={newAlert.symbol} onChange={e => setNewAlert(a => ({ ...a, symbol: e.target.value.toUpperCase() }))} placeholder="NVDA" style={{ width: '100%', background: '#232120', border: '1px solid #292524', borderRadius: 8, padding: '9px 12px', color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#a8a29e', marginBottom: 6 }}>Condition</label>
                <select value={newAlert.direction} onChange={e => setNewAlert(a => ({ ...a, direction: e.target.value }))} style={{ width: '100%', background: '#232120', border: '1px solid #292524', borderRadius: 8, padding: '9px 12px', color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, outline: 'none' }}>
                  <option value="above">Price above</option>
                  <option value="below">Price below</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, color: '#a8a29e', marginBottom: 6 }}>Target price</label>
                <input type="number" value={newAlert.target} onChange={e => setNewAlert(a => ({ ...a, target: e.target.value }))} placeholder="0.00" style={{ width: '100%', background: '#232120', border: '1px solid #292524', borderRadius: 8, padding: '9px 12px', color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, outline: 'none', boxSizing: 'border-box' }} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => setShowCreate(false)} style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', cursor: 'pointer', fontSize: 13 }}>Cancel</button>
              <button
                onClick={() => createMutation.mutate()}
                disabled={!newAlert.symbol || !newAlert.target}
                style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: newAlert.symbol && newAlert.target ? '#d6d3d1' : '#292524', color: newAlert.symbol && newAlert.target ? '#0c0a09' : '#a8a29e', cursor: newAlert.symbol && newAlert.target ? 'pointer' : 'not-allowed', fontSize: 13, fontWeight: 600 }}
              >
                {createMutation.isPending ? 'Creating...' : 'Create Alert'}
              </button>
            </div>
          </div>
        )}

        {/* SECTION: Active */}
        <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#a8a29e', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
          Active
          <div style={{ flex: 1, height: 1, background: '#292524' }} />
        </div>

        {alerts.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#a8a29e' }}>
            <Icon name="notifications_none" size={48} />
            <div style={{ fontSize: 15, fontWeight: 600, marginTop: 16, color: '#fafaf9' }}>No alerts yet</div>
            <div style={{ fontSize: 13, marginTop: 8 }}>Create an alert to get notified when a price target is hit</div>
          </div>
        ) : null}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
          {alerts.map((a: any) => {
            // API fields: alert_id, symbol, direction (above|below), target_price, active (bool)
            const alertId = a.alert_id || a.id
            const targetPrice = a.target_price ?? a.target ?? 0
            const currentPrice = a.current_price ?? 0
            const isActive = a.active !== undefined ? a.active : (a.status === 'active')
            const isTriggered = !!a.last_triggered_at
            const progress = getProgress(a)
            const progressColor = a.direction === 'above' ? '#22c55e' : '#ef4444'
            const statusColor = isTriggered ? '#f59e0b' : isActive ? '#22c55e' : '#a8a29e'
            const statusLabel = isTriggered ? 'Triggered' : isActive ? 'Active' : 'Paused'
            return (
              <div key={alertId} style={{ background: '#1c1917', border: `1px solid #292524`, borderRadius: 14, overflow: 'hidden' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px' }}>
                  {/* Status */}
                  <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8, minWidth: 80 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, boxShadow: isActive && !isTriggered ? `0 0 8px ${statusColor}` : 'none' }} />
                    <span style={{ fontSize: 11, fontWeight: 500, color: statusColor }}>{statusLabel}</span>
                  </div>
                  {/* Ticker */}
                  <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 15, fontWeight: 700, padding: '6px 12px', borderRadius: 8, background: '#232120', border: '1px solid #292524', letterSpacing: '0.02em', minWidth: 64, textAlign: 'center', flexShrink: 0 }}>
                    {a.symbol}
                  </div>
                  {/* Condition */}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 500 }}>
                      Price {a.direction || 'above'} {fmt(targetPrice)}
                    </div>
                    {currentPrice > 0 && (
                      <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>
                        Current: {fmt(currentPrice)} &nbsp;&middot;&nbsp; {Math.abs(((currentPrice - targetPrice) / targetPrice) * 100).toFixed(1)}% away
                      </div>
                    )}
                    {a.last_triggered_at && (
                      <div style={{ fontSize: 11, color: '#a8a29e', marginTop: 2 }}>
                        Triggered {new Date(a.last_triggered_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      </div>
                    )}
                  </div>
                  {/* Progress */}
                  {currentPrice > 0 && targetPrice > 0 && (
                    <div style={{ minWidth: 180 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#a8a29e', marginBottom: 6, fontVariantNumeric: 'tabular-nums' }}>
                        <span>{fmt(currentPrice)}</span>
                        <span>{fmt(targetPrice)}</span>
                      </div>
                      <div style={{ height: 4, background: '#232120', borderRadius: 999, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${progress}%`, borderRadius: 999, background: progressColor, transition: 'width 0.3s ease' }} />
                      </div>
                    </div>
                  )}
                  {/* Actions */}
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button
                      onClick={() => toggleMutation.mutate({ id: alertId, active: !isActive })}
                      style={{ width: 30, height: 30, borderRadius: 7, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                      title={isActive ? 'Pause' : 'Resume'}
                    >
                      <Icon name={isActive ? 'pause' : 'play_arrow'} size={15} />
                    </button>
                    <button
                      onClick={() => confirm('Delete this alert?') && deleteMutation.mutate(alertId)}
                      style={{ width: 30, height: 30, borderRadius: 7, border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.05)', color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                      <Icon name="delete" size={15} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </main>
    </div>
  )
}
