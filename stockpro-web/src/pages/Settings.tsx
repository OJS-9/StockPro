import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useUser } from '@clerk/clerk-react'
import toast from 'react-hot-toast'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ position: 'relative', width: 44, height: 24, cursor: 'pointer', display: 'inline-block' }}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }} />
      <div style={{ position: 'absolute', inset: 0, background: checked ? '#22c55e' : '#232120', border: `1px solid ${checked ? '#22c55e' : '#292524'}`, borderRadius: 100, transition: 'background 0.2s, border-color 0.2s' }} />
      <div style={{ position: 'absolute', top: 3, left: checked ? 23 : 3, width: 16, height: 16, background: checked ? '#fff' : '#a8a29e', borderRadius: '50%', transition: 'left 0.2s, background 0.2s' }} />
    </label>
  )
}

const NAV_ITEMS = [
  { id: 'profile', icon: 'person', label: 'Profile' },
  { id: 'notifications', icon: 'notifications', label: 'Notifications' },
  { id: 'research', icon: 'query_stats', label: 'Research defaults' },
  { id: 'telegram', icon: 'send', label: 'Telegram' },
  { id: 'plan', icon: 'card_membership', label: 'Plan' },
  { id: 'danger', icon: 'warning', label: 'Danger zone' },
]

export default function Settings() {
  const { user } = useUser()
  const api = useApiClient()
  const [activeSection, setActiveSection] = useState('profile')
  const [hasChanges, setHasChanges] = useState(false)

  const [notifs, setNotifs] = useState({
    price_alerts_telegram: true,
    price_alerts_email: false,
    weekly_summary: true,
    earnings_reminders: true,
    research_complete: true,
    marketing: false,
  })

  const [researchDefaults, setResearchDefaults] = useState({
    default_trade_type: 'Investment',
    include_technicals: true,
    include_news: true,
    include_risks: true,
  })

  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const res = await api.get('/api/settings')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  // /api/settings returns {profile: {user_id, display_name, is_pro, tier}, preferences: {...}}
  const prefs = settingsData?.preferences || {}
  const telegramConnected = prefs.telegram_connected || false
  const telegramUsername = prefs.telegram_username || null

  const saveMutation = useMutation({
    // PUT /api/settings: body is a patch merged into JSONB preferences
    mutationFn: async () => {
      const res = await api.put('/api/settings', {
        notifications: notifs,
        research_defaults: researchDefaults,
      })
      if (!res.ok) throw new Error('Failed')
    },
    onSuccess: () => {
      toast.success('Settings saved')
      setHasChanges(false)
    },
    onError: () => toast.error('Failed to save'),
  })

  const disconnectTelegramMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/api/telegram/disconnect', {})
      if (!res.ok) throw new Error('Failed')
    },
    onSuccess: () => toast.success('Telegram disconnected'),
    onError: () => toast.error('Failed to disconnect'),
  })

  const updateNotif = (key: string, val: boolean) => {
    setNotifs(n => ({ ...n, [key]: val }))
    setHasChanges(true)
  }

  const initials = user ? ((user.firstName?.[0] || '') + (user.lastName?.[0] || '')).toUpperCase() || 'U' : 'U'

  const settingRowStyle = {
    display: 'flex' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    padding: '16px 20px',
    borderBottom: '1px solid #292524',
    gap: 24,
  }

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '48px 48px 80px', display: 'grid', gridTemplateColumns: '220px 1fr', gap: 40, alignItems: 'start' }}>

        {/* SIDEBAR NAV */}
        <div style={{ position: 'sticky', top: 80 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#a8a29e', marginBottom: 12, padding: '0 10px' }}>Settings</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {NAV_ITEMS.map(({ id, icon, label }) => (
              <button
                key={id}
                onClick={() => setActiveSection(id)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 9, color: activeSection === id ? '#fafaf9' : '#a8a29e', fontSize: 13.5, fontWeight: 500, cursor: 'pointer', background: activeSection === id ? 'rgba(214,211,209,0.07)' : 'transparent', border: 'none', textAlign: 'left', transition: 'all 0.15s' }}
              >
                <Icon name={icon} size={17} />
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* CONTENT */}
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>
            {NAV_ITEMS.find(n => n.id === activeSection)?.label || 'Settings'}
          </h1>
          <p style={{ fontSize: 13, color: '#a8a29e', marginBottom: 36 }}>Manage your StockPro account preferences.</p>

          {/* PROFILE */}
          {activeSection === 'profile' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '20px', borderBottom: '1px solid #292524' }}>
                  <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'linear-gradient(135deg, #2d2b29, #3d3a37)', border: '2px solid #292524', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, fontWeight: 700, color: '#d6d3d1', fontFamily: 'Nunito, sans-serif', flexShrink: 0, overflow: 'hidden' }}>
                    {user?.imageUrl ? <img src={user.imageUrl} alt={initials} style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : initials}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 16, fontWeight: 700, marginBottom: 2 }}>
                      {user?.firstName} {user?.lastName}
                    </div>
                    <div style={{ fontSize: 13, color: '#a8a29e' }}>{user?.primaryEmailAddress?.emailAddress}</div>
                  </div>
                  <button style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: 'rgba(250,250,249,0.65)', fontSize: 12.5, fontWeight: 500, cursor: 'pointer' }}>
                    Edit profile
                  </button>
                </div>
                <div style={settingRowStyle}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>Display name</div>
                    <div style={{ fontSize: 12.5, color: '#a8a29e' }}>How your name appears in the app</div>
                  </div>
                  <input defaultValue={`${user?.firstName || ''} ${user?.lastName || ''}`.trim()} style={{ background: '#232120', border: '1px solid #292524', borderRadius: 8, color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, padding: '7px 12px', outline: 'none', width: 180 }} />
                </div>
                <div style={{ ...settingRowStyle, borderBottom: 'none' }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>Timezone</div>
                    <div style={{ fontSize: 12.5, color: '#a8a29e' }}>Used for alert scheduling and reports</div>
                  </div>
                  <select defaultValue="America/New_York" style={{ background: '#232120', border: '1px solid #292524', borderRadius: 8, color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, padding: '7px 28px 7px 10px', outline: 'none' }}>
                    <option value="America/New_York">Eastern Time</option>
                    <option value="America/Chicago">Central Time</option>
                    <option value="America/Los_Angeles">Pacific Time</option>
                    <option value="Europe/London">London</option>
                    <option value="Europe/Berlin">Berlin</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* NOTIFICATIONS */}
          {activeSection === 'notifications' && (
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              {[
                { key: 'price_alerts_telegram', name: 'Price alerts via Telegram', desc: 'Get notified when price alerts trigger on Telegram' },
                { key: 'price_alerts_email', name: 'Price alerts via email', desc: 'Get notified when price alerts trigger via email' },
                { key: 'weekly_summary', name: 'Weekly portfolio summary', desc: 'Receive a weekly P&L and portfolio overview' },
                { key: 'earnings_reminders', name: 'Earnings reminders', desc: 'Get reminded about upcoming earnings for watchlist stocks' },
                { key: 'research_complete', name: 'Research complete', desc: 'Notify when an AI research report is finished' },
                { key: 'marketing', name: 'Product updates', desc: 'News about new features and improvements' },
              ].map(({ key, name, desc }, i, arr) => (
                <div key={key} style={{ ...settingRowStyle, borderBottom: i < arr.length - 1 ? '1px solid #292524' : 'none' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{name}</div>
                    <div style={{ fontSize: 12.5, color: '#a8a29e' }}>{desc}</div>
                  </div>
                  <Toggle checked={notifs[key as keyof typeof notifs]} onChange={(v) => updateNotif(key, v)} />
                </div>
              ))}
            </div>
          )}

          {/* RESEARCH DEFAULTS */}
          {activeSection === 'research' && (
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={settingRowStyle}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>Default trade type</div>
                  <div style={{ fontSize: 12.5, color: '#a8a29e' }}>Pre-select this option when starting new research</div>
                </div>
                <select value={researchDefaults.default_trade_type} onChange={e => { setResearchDefaults(d => ({ ...d, default_trade_type: e.target.value })); setHasChanges(true) }} style={{ background: '#232120', border: '1px solid #292524', borderRadius: 8, color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, padding: '7px 28px 7px 10px', outline: 'none' }}>
                  <option>Day Trade</option>
                  <option>Swing Trade</option>
                  <option>Investment</option>
                </select>
              </div>
              {[
                { key: 'include_technicals', name: 'Include technical analysis', desc: 'Chart patterns, support/resistance levels' },
                { key: 'include_news', name: 'Include news analysis', desc: 'Recent news and sentiment analysis' },
                { key: 'include_risks', name: 'Include risk analysis', desc: 'Risk factors and downside scenarios' },
              ].map(({ key, name, desc }, i) => (
                <div key={key} style={{ ...settingRowStyle, borderBottom: i < 2 ? '1px solid #292524' : 'none' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{name}</div>
                    <div style={{ fontSize: 12.5, color: '#a8a29e' }}>{desc}</div>
                  </div>
                  <Toggle checked={researchDefaults[key as keyof typeof researchDefaults] as boolean} onChange={(v) => { setResearchDefaults(d => ({ ...d, [key]: v })); setHasChanges(true) }} />
                </div>
              ))}
            </div>
          )}

          {/* TELEGRAM */}
          {activeSection === 'telegram' && (
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '18px 20px' }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(38,145,218,0.1)', border: '1px solid rgba(38,145,218,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="#26a8da"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z" /></svg>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>Telegram</div>
                  <div style={{ fontSize: 12.5, color: '#a8a29e' }}>
                    {telegramConnected ? `Connected as @${telegramUsername}` : 'Connect to receive real-time price alerts and summaries'}
                  </div>
                </div>
                {telegramConnected ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 500, padding: '4px 10px', borderRadius: 100, background: 'rgba(34,197,94,0.08)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.2)' }}>
                      <Icon name="check_circle" size={13} filled /> Connected
                    </span>
                    <button onClick={() => disconnectTelegramMutation.mutate()} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: 'rgba(250,250,249,0.65)', fontSize: 12.5, fontWeight: 500, cursor: 'pointer' }}>
                      Disconnect
                    </button>
                  </div>
                ) : (
                  <button style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #292524', background: '#232120', color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
                    Connect Telegram
                  </button>
                )}
              </div>
            </div>
          )}

          {/* DANGER ZONE */}
          {activeSection === 'danger' && (
            <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 14, overflow: 'hidden' }}>
              {[
                { name: 'Clear all reports', desc: 'Delete all AI research reports. This cannot be undone.', btnLabel: 'Clear reports' },
                { name: 'Delete all portfolios', desc: 'Remove all portfolios and transaction history permanently.', btnLabel: 'Delete portfolios' },
                { name: 'Delete account', desc: 'Permanently delete your account and all associated data.', btnLabel: 'Delete account' },
              ].map(({ name, desc, btnLabel }, i, arr) => (
                <div key={name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: i < arr.length - 1 ? '1px solid rgba(239,68,68,0.15)' : 'none', gap: 24 }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#ef4444', marginBottom: 2 }}>{name}</div>
                    <div style={{ fontSize: 12.5, color: 'rgba(239,68,68,0.65)' }}>{desc}</div>
                  </div>
                  <button onClick={() => confirm(`Are you sure you want to ${btnLabel.toLowerCase()}?`)} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.08)', color: '#ef4444', fontSize: 12.5, fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                    {btnLabel}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* SAVE BANNER */}
      {hasChanges && (
        <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '16px 24px', background: 'rgba(12,10,9,0.96)', backdropFilter: 'blur(16px)', borderTop: '1px solid #292524' }}>
          <span style={{ fontSize: 13, color: '#a8a29e' }}>You have <strong style={{ color: '#fafaf9', fontWeight: 500 }}>unsaved changes</strong></span>
          <button onClick={() => setHasChanges(false)} style={{ padding: '9px 16px', borderRadius: 9, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 13.5, fontWeight: 500, cursor: 'pointer' }}>
            Discard
          </button>
          <button onClick={() => saveMutation.mutate()} style={{ padding: '9px 22px', borderRadius: 9, border: 'none', background: '#d6d3d1', color: '#0c0a09', fontSize: 13.5, fontWeight: 600, cursor: 'pointer' }}>
            {saveMutation.isPending ? 'Saving...' : 'Save changes'}
          </button>
        </div>
      )}
    </div>
  )
}
