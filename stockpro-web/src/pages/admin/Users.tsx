import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { useApiClient } from '../../api/client'
import Icon from '../../components/Icon'

function formatDate(iso: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function timeAgo(iso: string) {
  if (!iso) return 'Never'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

type SortField = 'created_at' | 'username' | 'tier' | 'last_active_at'

export default function Users() {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<SortField>('created_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')

  // Debounce search input
  const [timer, setTimer] = useState<ReturnType<typeof setTimeout> | null>(null)
  const handleSearch = (val: string) => {
    setSearch(val)
    if (timer) clearTimeout(timer)
    const t = setTimeout(() => {
      setDebouncedSearch(val)
      setPage(1)
    }, 400)
    setTimer(t)
  }

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users', debouncedSearch, page, sort, order],
    queryFn: async () => {
      const params = new URLSearchParams({
        search: debouncedSearch, page: String(page), sort, order,
      })
      const res = await api.get(`/api/admin/users?${params}`)
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const toggleDisable = useMutation({
    mutationFn: async ({ userId, disabled }: { userId: string; disabled: boolean }) => {
      const res = await api.patch(`/api/admin/users/${userId}`, { disabled })
      if (!res.ok) throw new Error('Failed')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success('User updated')
    },
    onError: () => toast.error('Failed to update user'),
  })

  const impersonate = useMutation({
    mutationFn: async (userId: string) => {
      const res = await api.post(`/api/admin/users/${userId}/impersonate`, {})
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
    onSuccess: (data) => {
      if (data?.url) {
        window.open(data.url, '_blank')
      } else {
        toast.error('No impersonation URL returned')
      }
    },
    onError: () => toast.error('Impersonation failed'),
  })

  const handleSort = (field: SortField) => {
    if (sort === field) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(field)
      setOrder('desc')
    }
    setPage(1)
  }

  const sortIcon = (field: SortField) => {
    if (sort !== field) return null
    return <Icon name={order === 'asc' ? 'arrow_upward' : 'arrow_downward'} size={14} />
  }

  const users = data?.users ?? []
  const totalPages = data?.pages ?? 1

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h1 style={{ fontFamily: "'Nunito', sans-serif", fontWeight: 700, fontSize: 24, color: '#fafaf9', margin: 0 }}>
          Users
        </h1>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['admin-users'] })}
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

      {/* Search */}
      <div style={{ marginBottom: 20 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: '#1c1917', border: '1px solid #292524', borderRadius: 10,
          padding: '8px 14px', maxWidth: 360,
        }}>
          <Icon name="search" size={18} style={{ color: '#78716c' }} />
          <input
            type="text"
            placeholder="Search by name..."
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            style={{
              background: 'transparent', border: 'none', outline: 'none',
              color: '#fafaf9', fontSize: 14, width: '100%',
            }}
          />
        </div>
      </div>

      {/* Table */}
      <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #292524' }}>
              <Th onClick={() => handleSort('username')}>Name {sortIcon('username')}</Th>
              <Th>Email</Th>
              <Th onClick={() => handleSort('tier')}>Tier {sortIcon('tier')}</Th>
              <Th onClick={() => handleSort('created_at')}>Signed Up {sortIcon('created_at')}</Th>
              <Th onClick={() => handleSort('last_active_at')}>Last Active {sortIcon('last_active_at')}</Th>
              <Th>Status</Th>
              <Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={7} style={{ ...tdStyle, color: '#78716c' }}>Loading...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={7} style={{ ...tdStyle, color: '#78716c' }}>No users found</td></tr>
            ) : users.map((u: any) => (
              <tr key={u.user_id} style={{ borderBottom: '1px solid #1a1816' }}>
                <td style={{ ...tdStyle, fontWeight: 500, color: '#fafaf9' }}>{u.username}</td>
                <td style={{ ...tdStyle, color: '#a8a29e', fontSize: 12 }}>{u.email}</td>
                <td style={tdStyle}>
                  <span style={{
                    background: u.tier === 'free' ? '#292524' : '#1a2e1a',
                    color: u.tier === 'free' ? '#a8a29e' : '#22c55e',
                    padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                  }}>
                    {u.tier}
                  </span>
                </td>
                <td style={{ ...tdStyle, color: '#78716c', fontSize: 12 }}>{formatDate(u.created_at)}</td>
                <td style={{ ...tdStyle, color: '#78716c', fontSize: 12 }}>{timeAgo(u.last_active_at)}</td>
                <td style={tdStyle}>
                  <span style={{
                    color: u.disabled ? '#ef4444' : '#22c55e',
                    fontSize: 12, fontWeight: 600,
                  }}>
                    {u.disabled ? 'Disabled' : 'Active'}
                  </span>
                </td>
                <td style={{ ...tdStyle, display: 'flex', gap: 6 }}>
                  <ActionBtn
                    icon={u.disabled ? 'check_circle' : 'block'}
                    title={u.disabled ? 'Enable' : 'Disable'}
                    onClick={() => toggleDisable.mutate({ userId: u.user_id, disabled: !u.disabled })}
                  />
                  <ActionBtn
                    icon="supervisor_account"
                    title="Impersonate"
                    onClick={() => impersonate.mutate(u.user_id)}
                  />
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

function Th({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <th
      onClick={onClick}
      style={{
        textAlign: 'left', padding: '12px 14px', fontSize: 12, fontWeight: 600,
        color: '#78716c', textTransform: 'uppercase', letterSpacing: '0.04em',
        cursor: onClick ? 'pointer' : 'default', userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        {children}
      </span>
    </th>
  )
}

function ActionBtn({ icon, title, onClick }: { icon: string; title: string; onClick: () => void }) {
  return (
    <button
      title={title}
      onClick={onClick}
      style={{
        background: '#292524', border: '1px solid #292524', borderRadius: 8,
        padding: '5px 8px', cursor: 'pointer', color: '#a8a29e',
        display: 'flex', alignItems: 'center',
      }}
    >
      <Icon name={icon} size={16} />
    </button>
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
