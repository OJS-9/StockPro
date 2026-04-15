import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '../../api/client'
import Icon from '../../components/Icon'

function timeAgo(iso: string) {
  if (!iso) return '-'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

const EVENT_COLORS: Record<string, string> = {
  signup: '#3b82f6',
  research_complete: '#22c55e',
  alert_triggered: '#f59e0b',
  config_changed: '#a855f7',
  config_deleted: '#ef4444',
}

export default function Logs() {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const [eventType, setEventType] = useState('')
  const [page, setPage] = useState(1)

  const { data: typesData } = useQuery({
    queryKey: ['admin-event-types'],
    queryFn: async () => {
      const res = await api.get('/api/admin/events/types')
      if (!res.ok) return { types: [] }
      return res.json()
    },
  })

  const { data, isLoading } = useQuery({
    queryKey: ['admin-events', eventType, page],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page) })
      if (eventType) params.set('event_type', eventType)
      const res = await api.get(`/api/admin/events?${params}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['admin-events'] })
    queryClient.invalidateQueries({ queryKey: ['admin-event-types'] })
  }

  const events = data?.events ?? []
  const totalPages = data?.pages ?? 1
  const eventTypes = typesData?.types ?? []

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h1 style={{ fontFamily: "'Nunito', sans-serif", fontWeight: 700, fontSize: 24, color: '#fafaf9', margin: 0 }}>
          Logs
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

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <select
          value={eventType}
          onChange={(e) => { setEventType(e.target.value); setPage(1) }}
          style={{
            background: '#1c1917', border: '1px solid #292524', borderRadius: 10,
            padding: '8px 14px', color: '#fafaf9', fontSize: 13, outline: 'none',
            cursor: 'pointer', minWidth: 160,
          }}
        >
          <option value="">All event types</option>
          {eventTypes.map((t: string) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {/* Events table */}
      <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #292524' }}>
              <Th>Type</Th>
              <Th>User</Th>
              <Th>Details</Th>
              <Th>Time</Th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={4} style={{ ...tdStyle, color: '#78716c' }}>Loading...</td></tr>
            ) : events.length === 0 ? (
              <tr><td colSpan={4} style={{ ...tdStyle, color: '#78716c' }}>No events found</td></tr>
            ) : events.map((ev: any) => (
              <tr key={ev.event_id} style={{ borderBottom: '1px solid #1a1816' }}>
                <td style={tdStyle}>
                  <span style={{
                    display: 'inline-block',
                    padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                    background: `${EVENT_COLORS[ev.event_type] ?? '#78716c'}20`,
                    color: EVENT_COLORS[ev.event_type] ?? '#a8a29e',
                    border: `1px solid ${EVENT_COLORS[ev.event_type] ?? '#78716c'}40`,
                  }}>
                    {ev.event_type}
                  </span>
                </td>
                <td style={{ ...tdStyle, color: '#a8a29e', fontSize: 12 }}>
                  {ev.username || ev.user_id?.slice(0, 12) || '-'}
                </td>
                <td style={{ ...tdStyle, color: '#78716c', fontSize: 12, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {formatPayload(ev.payload)}
                </td>
                <td style={{ ...tdStyle, color: '#57534e', fontSize: 12, whiteSpace: 'nowrap' }}>
                  {timeAgo(ev.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, marginTop: 20 }}>
          <PaginationBtn disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <Icon name="chevron_left" size={18} />
          </PaginationBtn>
          <span style={{ fontSize: 13, color: '#a8a29e' }}>
            Page {page} of {totalPages}
          </span>
          <PaginationBtn disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            <Icon name="chevron_right" size={18} />
          </PaginationBtn>
        </div>
      )}
    </div>
  )
}

function formatPayload(payload: any): string {
  if (!payload || typeof payload !== 'object') return '-'
  const parts: string[] = []
  for (const [k, v] of Object.entries(payload)) {
    if (v != null && v !== '') parts.push(`${k}: ${v}`)
  }
  return parts.join(', ') || '-'
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th style={{
      textAlign: 'left', padding: '12px 14px', fontSize: 12, fontWeight: 600,
      color: '#78716c', textTransform: 'uppercase', letterSpacing: '0.04em',
    }}>
      {children}
    </th>
  )
}

function PaginationBtn({ children, disabled, onClick }: { children: React.ReactNode; disabled: boolean; onClick: () => void }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      style={{
        background: disabled ? '#1c1917' : '#292524',
        border: '1px solid #292524', borderRadius: 8,
        padding: '6px 10px', cursor: disabled ? 'default' : 'pointer',
        color: disabled ? '#44403c' : '#d6d3d1',
        display: 'flex', alignItems: 'center',
      }}
    >
      {children}
    </button>
  )
}

const tdStyle: React.CSSProperties = {
  padding: '12px 14px', fontSize: 13, color: '#d6d3d1',
}
