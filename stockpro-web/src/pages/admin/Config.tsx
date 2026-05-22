import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { useApiClient } from '../../api/client'
import Icon from '../../components/Icon'

// Default config keys with their descriptions
const CONFIG_SECTIONS = [
  {
    title: 'Rate Limits',
    icon: 'speed',
    keys: [
      { key: 'rate_limit_research', label: 'Research', placeholder: '30 per hour' },
      { key: 'rate_limit_report_gen', label: 'Report Generation', placeholder: '15 per hour' },
      { key: 'rate_limit_chat', label: 'Chat (Q&A)', placeholder: '40 per hour' },
      { key: 'rate_limit_watchlist_news', label: 'Watchlist News', placeholder: '30 per hour' },
    ],
  },
  {
    title: 'Model Assignments',
    icon: 'smart_toy',
    keys: [
      { key: 'model_orchestrator', label: 'Orchestrator', placeholder: 'gemini-2.5-flash' },
      { key: 'model_planner', label: 'Planner', placeholder: 'gemini-2.5-flash' },
      { key: 'model_specialized', label: 'Specialized Agent', placeholder: 'gemini-2.5-pro' },
      { key: 'model_synthesis', label: 'Synthesis Agent', placeholder: 'gemini-2.5-pro' },
      { key: 'model_chat', label: 'Chat Agent', placeholder: 'gemini-2.5-flash' },
    ],
  },
  {
    title: 'Feature Flags',
    icon: 'toggle_on',
    keys: [
      { key: 'feature_telegram_alerts', label: 'Telegram Alerts', placeholder: 'true' },
      { key: 'feature_csv_import', label: 'CSV Import', placeholder: 'true' },
      { key: 'feature_watchlist_news', label: 'Watchlist News Recap', placeholder: 'true' },
      { key: 'feature_paper_trading', label: 'Paper Trading (Phase 2)', placeholder: 'false' },
    ],
  },
  {
    title: 'Pricing Tiers',
    icon: 'payments',
    keys: [
      { key: 'tier_free_report_limit', label: 'Free Tier Report Limit (monthly)', placeholder: '5' },
      { key: 'tier_pro_report_limit', label: 'Pro Tier Report Limit (monthly)', placeholder: '100' },
      { key: 'tier_pro_price_usd', label: 'Pro Price (USD/month)', placeholder: '29' },
    ],
  },
]

export default function Config() {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const [editKey, setEditKey] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['admin-config'],
    queryFn: async () => {
      const res = await api.get('/api/admin/config')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const saveMutation = useMutation({
    mutationFn: async ({ key, value }: { key: string; value: string }) => {
      const res = await api.put('/api/admin/config', { key, value })
      if (!res.ok) throw new Error('Failed')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-config'] })
      setEditKey(null)
      toast.success('Config saved')
    },
    onError: () => toast.error('Failed to save config'),
  })

  const deleteMutation = useMutation({
    mutationFn: async (key: string) => {
      const res = await api.delete(`/api/admin/config/${key}`)
      if (!res.ok) throw new Error('Failed')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-config'] })
      toast.success('Config removed')
    },
    onError: () => toast.error('Failed to remove config'),
  })

  const startEdit = (key: string) => {
    const current = data?.[key]?.value
    setEditKey(key)
    setEditValue(current != null ? String(current) : '')
  }

  const saveEdit = () => {
    if (!editKey) return
    saveMutation.mutate({ key: editKey, value: editValue })
  }

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin-config'] })

  const configData: Record<string, any> = data ?? {}

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h1 style={{ fontFamily: "'Nunito', sans-serif", fontWeight: 700, fontSize: 24, color: '#fafaf9', margin: 0 }}>
          Config
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {CONFIG_SECTIONS.map((section) => (
            <div key={section.title} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <Icon name={section.icon} size={20} style={{ color: '#78716c' }} />
                <h2 style={{ fontSize: 15, fontWeight: 600, color: '#d6d3d1', margin: 0 }}>{section.title}</h2>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {section.keys.map(({ key, label, placeholder }) => {
                  const stored = configData[key]
                  const currentValue = stored?.value
                  const isEditing = editKey === key

                  return (
                    <div
                      key={key}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        padding: '10px 14px', borderRadius: 10,
                        background: isEditing ? '#292524' : 'transparent',
                        border: '1px solid transparent',
                      }}
                    >
                      <div style={{ flex: '0 0 200px' }}>
                        <span style={{ fontSize: 13, color: '#d6d3d1', fontWeight: 500 }}>{label}</span>
                      </div>

                      {isEditing ? (
                        <>
                          <input
                            autoFocus
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') saveEdit(); if (e.key === 'Escape') setEditKey(null) }}
                            placeholder={placeholder}
                            style={{
                              flex: 1, background: '#1c1917', border: '1px solid #292524', borderRadius: 8,
                              padding: '6px 12px', color: '#fafaf9', fontSize: 13, outline: 'none',
                            }}
                          />
                          <button
                            onClick={saveEdit}
                            style={{
                              background: '#292524', border: '1px solid #292524', borderRadius: 8,
                              padding: '5px 12px', cursor: 'pointer', color: '#22c55e', fontSize: 12, fontWeight: 600,
                            }}
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditKey(null)}
                            style={{
                              background: 'transparent', border: 'none', cursor: 'pointer',
                              color: '#78716c', fontSize: 12,
                            }}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <div style={{ flex: 1, fontSize: 13 }}>
                            {currentValue != null ? (
                              <span style={{ color: '#fafaf9', fontFamily: 'monospace' }}>
                                {String(currentValue)}
                              </span>
                            ) : (
                              <span style={{ color: '#57534e', fontStyle: 'italic' }}>
                                {placeholder} (default)
                              </span>
                            )}
                          </div>
                          <button
                            onClick={() => startEdit(key)}
                            title="Edit"
                            style={{
                              background: 'transparent', border: '1px solid #292524', borderRadius: 8,
                              padding: '5px 8px', cursor: 'pointer', color: '#a8a29e',
                              display: 'flex', alignItems: 'center',
                            }}
                          >
                            <Icon name="edit" size={14} />
                          </button>
                          {currentValue != null && (
                            <button
                              onClick={() => deleteMutation.mutate(key)}
                              title="Reset to default"
                              style={{
                                background: 'transparent', border: '1px solid #292524', borderRadius: 8,
                                padding: '5px 8px', cursor: 'pointer', color: '#78716c',
                                display: 'flex', alignItems: 'center',
                              }}
                            >
                              <Icon name="restart_alt" size={14} />
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
