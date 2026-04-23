import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useUser } from '@clerk/clerk-react'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useLanguage } from '../LanguageContext'

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ position: 'relative', width: 44, height: 24, cursor: 'pointer', display: 'inline-block' }}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }} />
      <div style={{ position: 'absolute', inset: 0, background: checked ? '#22c55e' : '#232120', border: `1px solid ${checked ? '#22c55e' : '#292524'}`, borderRadius: 100, transition: 'background 0.2s, border-color 0.2s' }} />
      <div style={{ position: 'absolute', top: 3, insetInlineStart: checked ? 23 : 3, width: 16, height: 16, background: checked ? '#fff' : '#a8a29e', borderRadius: '50%', transition: 'inset-inline-start 0.2s, background 0.2s' }} />
    </label>
  )
}

const NAV_ITEMS = [
  { id: 'profile', icon: 'person', tKey: 'settings.profile' },
  { id: 'language', icon: 'translate', tKey: 'settings.language' },
  { id: 'notifications', icon: 'notifications', tKey: 'settings.notifications' },
  { id: 'research', icon: 'query_stats', tKey: 'settings.researchDefaults' },
  { id: 'telegram', icon: 'send', tKey: 'settings.telegram' },
  { id: 'cli', icon: 'terminal', tKey: 'settings.cli' },
  { id: 'plan', icon: 'card_membership', tKey: 'settings.plan' },
  { id: 'danger', icon: 'warning', tKey: 'settings.dangerZone' },
]

export default function Settings() {
  const { user } = useUser()
  const api = useApiClient()
  const { lang, setLang } = useLanguage()
  const { t } = useTranslation()
  const initialSection = (() => {
    if (typeof window === 'undefined') return 'profile'
    const s = new URLSearchParams(window.location.search).get('section')
    return NAV_ITEMS.some(n => n.id === s) ? (s as string) : 'profile'
  })()
  const [activeSection, setActiveSection] = useState(initialSection)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    if (activeSection === 'plan' && params.get('status') === 'success') {
      toast.success('Subscription activated')
      params.delete('status')
      const qs = params.toString()
      window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : ''))
    }
  }, [activeSection])
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
      toast.success(t('settings.saveChanges'))
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
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#a8a29e', marginBottom: 12, padding: '0 10px' }}>{t('settings.settings')}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {NAV_ITEMS.map(({ id, icon, tKey }) => (
              <button
                key={id}
                onClick={() => setActiveSection(id)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 9, color: activeSection === id ? '#fafaf9' : '#a8a29e', fontSize: 13.5, fontWeight: 500, cursor: 'pointer', background: activeSection === id ? 'rgba(214,211,209,0.07)' : 'transparent', border: 'none', textAlign: 'start', transition: 'all 0.15s' }}
              >
                <Icon name={icon} size={17} />
                {t(tKey)}
              </button>
            ))}
          </div>
        </div>

        {/* CONTENT */}
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 4 }}>
            {t(NAV_ITEMS.find(n => n.id === activeSection)?.tKey || 'settings.settings')}
          </h1>
          <p style={{ fontSize: 13, color: '#a8a29e', marginBottom: 36 }}>{t('settings.managePrefs')}</p>

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
                    {t('settings.editProfile')}
                  </button>
                </div>
                <div style={settingRowStyle}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{t('settings.displayName')}</div>
                    <div style={{ fontSize: 12.5, color: '#a8a29e' }}>{t('settings.displayNameDesc')}</div>
                  </div>
                  <input defaultValue={`${user?.firstName || ''} ${user?.lastName || ''}`.trim()} style={{ background: '#232120', border: '1px solid #292524', borderRadius: 8, color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, padding: '7px 12px', outline: 'none', width: 180 }} />
                </div>
                <div style={{ ...settingRowStyle, borderBottom: 'none' }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{t('settings.timezone')}</div>
                    <div style={{ fontSize: 12.5, color: '#a8a29e' }}>{t('settings.timezoneDesc')}</div>
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

          {/* LANGUAGE */}
          {activeSection === 'language' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {([
                  { code: 'en' as const, name: 'English', native: 'English' },
                  { code: 'he' as const, name: 'Hebrew', native: '\u05E2\u05D1\u05E8\u05D9\u05EA' },
                ] as const).map(({ code, name, native }) => (
                  <button
                    key={code}
                    onClick={() => setLang(code)}
                    style={{
                      position: 'relative',
                      background: '#1c1917',
                      border: `1px solid ${lang === code ? '#d6d3d1' : '#292524'}`,
                      borderRadius: 14,
                      padding: '20px',
                      cursor: 'pointer',
                      textAlign: 'start',
                      transition: 'border-color 0.15s',
                    }}
                  >
                    {lang === code && (
                      <div style={{ position: 'absolute', top: 12, insetInlineEnd: 12 }}>
                        <Icon name="check_circle" size={20} filled />
                      </div>
                    )}
                    <div style={{ fontSize: 15, fontWeight: 600, color: '#fafaf9', marginBottom: 4 }}>{name}</div>
                    <div style={{ fontSize: 13, color: '#a8a29e' }}>{native}</div>
                  </button>
                ))}
              </div>
              <p style={{ fontSize: 12.5, color: '#57534e', margin: 0 }}>
                {t('settings.languageChangeDesc')}
              </p>
            </div>
          )}

          {/* NOTIFICATIONS */}
          {activeSection === 'notifications' && (
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
              {[
                { key: 'price_alerts_telegram', nameKey: 'settings.priceAlertsTelegram', descKey: 'settings.priceAlertsTelegramDesc' },
                { key: 'price_alerts_email', nameKey: 'settings.priceAlertsEmail', descKey: 'settings.priceAlertsEmailDesc' },
                { key: 'weekly_summary', nameKey: 'settings.weeklySummary', descKey: 'settings.weeklySummaryDesc' },
                { key: 'earnings_reminders', nameKey: 'settings.earningsReminders', descKey: 'settings.earningsRemindersDesc' },
                { key: 'research_complete', nameKey: 'settings.researchComplete', descKey: 'settings.researchCompleteDesc' },
                { key: 'marketing', nameKey: 'settings.productUpdates', descKey: 'settings.productUpdatesDesc' },
              ].map(({ key, nameKey, descKey }, i, arr) => (
                <div key={key} style={{ ...settingRowStyle, borderBottom: i < arr.length - 1 ? '1px solid #292524' : 'none' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{t(nameKey)}</div>
                    <div style={{ fontSize: 12.5, color: '#a8a29e' }}>{t(descKey)}</div>
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
                  <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{t('settings.defaultTradeType')}</div>
                  <div style={{ fontSize: 12.5, color: '#a8a29e' }}>{t('settings.defaultTradeTypeDesc')}</div>
                </div>
                <select value={researchDefaults.default_trade_type} onChange={e => { setResearchDefaults(d => ({ ...d, default_trade_type: e.target.value })); setHasChanges(true) }} style={{ background: '#232120', border: '1px solid #292524', borderRadius: 8, color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, padding: '7px 28px 7px 10px', outline: 'none' }}>
                  <option>Day Trade</option>
                  <option>Swing Trade</option>
                  <option>Investment</option>
                </select>
              </div>
              {[
                { key: 'include_technicals', nameKey: 'settings.includeTechnicals', descKey: 'settings.includeTechnicalsDesc' },
                { key: 'include_news', nameKey: 'settings.includeNews', descKey: 'settings.includeNewsDesc' },
                { key: 'include_risks', nameKey: 'settings.includeRisks', descKey: 'settings.includeRisksDesc' },
              ].map(({ key, nameKey, descKey }, i) => (
                <div key={key} style={{ ...settingRowStyle, borderBottom: i < 2 ? '1px solid #292524' : 'none' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{t(nameKey)}</div>
                    <div style={{ fontSize: 12.5, color: '#a8a29e' }}>{t(descKey)}</div>
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
                  <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{t('settings.telegram')}</div>
                  <div style={{ fontSize: 12.5, color: '#a8a29e' }}>
                    {telegramConnected ? `Connected as @${telegramUsername}` : t('settings.telegramDesc')}
                  </div>
                </div>
                {telegramConnected ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 500, padding: '4px 10px', borderRadius: 100, background: 'rgba(34,197,94,0.08)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.2)' }}>
                      <Icon name="check_circle" size={13} filled /> {t('settings.connected')}
                    </span>
                    <button onClick={() => disconnectTelegramMutation.mutate()} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #292524', background: 'transparent', color: 'rgba(250,250,249,0.65)', fontSize: 12.5, fontWeight: 500, cursor: 'pointer' }}>
                      {t('settings.disconnect')}
                    </button>
                  </div>
                ) : (
                  <button style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #292524', background: '#232120', color: '#fafaf9', fontFamily: 'Inter, sans-serif', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
                    {t('settings.connectTelegram')}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* CLI TOKENS */}
          {activeSection === 'cli' && <CliTokensSection />}

          {/* PLAN */}
          {activeSection === 'plan' && <PlanSection />}

          {/* DANGER ZONE */}
          {activeSection === 'danger' && (
            <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 14, overflow: 'hidden' }}>
              {[
                { nameKey: 'settings.clearReports', descKey: 'settings.clearReportsDesc', btnKey: 'settings.clearReportsBtn' },
                { nameKey: 'settings.deletePortfolios', descKey: 'settings.deletePortfoliosDesc', btnKey: 'settings.deletePortfoliosBtn' },
                { nameKey: 'settings.deleteAccount', descKey: 'settings.deleteAccountDesc', btnKey: 'settings.deleteAccountBtn' },
              ].map(({ nameKey, descKey, btnKey }, i, arr) => (
                <div key={nameKey} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: i < arr.length - 1 ? '1px solid rgba(239,68,68,0.15)' : 'none', gap: 24 }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: '#ef4444', marginBottom: 2 }}>{t(nameKey)}</div>
                    <div style={{ fontSize: 12.5, color: 'rgba(239,68,68,0.65)' }}>{t(descKey)}</div>
                  </div>
                  <button onClick={() => confirm(`Are you sure you want to ${t(btnKey).toLowerCase()}?`)} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.08)', color: '#ef4444', fontSize: 12.5, fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                    {t(btnKey)}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* CLI tokens section — intentionally outside the save-banner mutation flow */}

      {/* SAVE BANNER */}
      {hasChanges && (
        <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '16px 24px', background: 'rgba(12,10,9,0.96)', backdropFilter: 'blur(16px)', borderTop: '1px solid #292524' }}>
          <span style={{ fontSize: 13, color: '#a8a29e' }}>{t('settings.unsavedChanges')} <strong style={{ color: '#fafaf9', fontWeight: 500 }}>{t('settings.unsavedChangesStrong')}</strong></span>
          <button onClick={() => setHasChanges(false)} style={{ padding: '9px 16px', borderRadius: 9, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 13.5, fontWeight: 500, cursor: 'pointer' }}>
            {t('settings.discard')}
          </button>
          <button onClick={() => saveMutation.mutate()} style={{ padding: '9px 22px', borderRadius: 9, border: 'none', background: '#d6d3d1', color: '#0c0a09', fontSize: 13.5, fontWeight: 600, cursor: 'pointer' }}>
            {saveMutation.isPending ? t('settings.saving') : t('settings.saveChanges')}
          </button>
        </div>
      )}
    </div>
  )
}

function CliTokensSection() {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const [newName, setNewName] = useState('')
  const [newToken, setNewToken] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['cli-tokens'],
    queryFn: async () => {
      const res = await api.get('/api/tokens')
      if (!res.ok) throw new Error('Failed to load tokens')
      return res.json() as Promise<{ tokens: Array<{ id: string; name: string; prefix: string; created_at: string; last_used_at: string | null }> }>
    },
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/api/tokens', { name: newName || 'CLI token' })
      if (!res.ok) throw new Error('Failed to create token')
      return res.json() as Promise<{ id: string; access_token: string }>
    },
    onSuccess: (resp) => {
      setNewToken(resp.access_token)
      setNewName('')
      queryClient.invalidateQueries({ queryKey: ['cli-tokens'] })
    },
    onError: () => toast.error('Failed to create token'),
  })

  const revokeMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await api.delete(`/api/tokens/${id}`)
      if (!res.ok) throw new Error('Failed to revoke')
    },
    onSuccess: () => {
      toast.success('Token revoked')
      queryClient.invalidateQueries({ queryKey: ['cli-tokens'] })
    },
    onError: () => toast.error('Failed to revoke token'),
  })

  const tokens = data?.tokens ?? []
  const rowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: '1px solid #292524', gap: 16 } as const

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <p style={{ fontSize: 13, color: '#a8a29e', margin: 0 }}>
        Long-lived tokens for the <code style={{ color: '#d6d3d1' }}>stockpro</code> CLI and headless agents. Set the token as <code style={{ color: '#d6d3d1' }}>STOCKPRO_TOKEN</code> or run <code style={{ color: '#d6d3d1' }}>stockpro auth device-login</code>.
      </p>

      {newToken && (
        <div style={{ background: '#1c1917', border: '1px solid #22c55e', borderRadius: 12, padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#22c55e' }}>Copy this token now</div>
          <div style={{ fontSize: 12, color: '#a8a29e' }}>It will never be shown again.</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <code style={{ flex: 1, background: '#0c0a09', border: '1px solid #292524', borderRadius: 8, padding: '10px 12px', fontFamily: 'ui-monospace, monospace', fontSize: 12, color: '#fafaf9', wordBreak: 'break-all' }}>{newToken}</code>
            <button
              onClick={() => { navigator.clipboard.writeText(newToken); toast.success('Copied') }}
              style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid #292524', background: '#232120', color: '#fafaf9', fontSize: 12.5, fontWeight: 500, cursor: 'pointer' }}
            >
              Copy
            </button>
          </div>
          <button onClick={() => setNewToken(null)} style={{ alignSelf: 'start', background: 'transparent', border: 0, color: '#a8a29e', fontSize: 12, cursor: 'pointer', marginTop: 4, padding: 0 }}>
            I saved it
          </button>
        </div>
      )}

      <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: 16, display: 'flex', gap: 8 }}>
        <input
          placeholder="Token name (e.g. laptop, serverless agent)"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          style={{ flex: 1, background: '#232120', border: '1px solid #292524', borderRadius: 8, color: '#fafaf9', fontSize: 13, padding: '9px 12px', outline: 'none' }}
        />
        <button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
        >
          {createMutation.isPending ? 'Creating...' : 'Create token'}
        </button>
      </div>

      <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, overflow: 'hidden' }}>
        {tokens.length === 0 ? (
          <div style={{ padding: 20, fontSize: 13, color: '#a8a29e', textAlign: 'center' }}>No tokens yet. Create one above, or run <code>stockpro auth device-login</code>.</div>
        ) : (
          tokens.map((t, i) => (
            <div key={t.id} style={{ ...rowStyle, borderBottom: i < tokens.length - 1 ? '1px solid #292524' : 'none' }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{t.name}</div>
                <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 3, fontFamily: 'ui-monospace, monospace' }}>
                  {t.prefix}... &middot; created {new Date(t.created_at).toLocaleDateString()}
                  {t.last_used_at && ` \u00B7 last used ${new Date(t.last_used_at).toLocaleDateString()}`}
                </div>
              </div>
              <button
                onClick={() => { if (confirm(`Revoke ${t.name}?`)) revokeMutation.mutate(t.id) }}
                style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.08)', color: '#ef4444', fontSize: 12.5, fontWeight: 500, cursor: 'pointer' }}
              >
                Revoke
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

type PlanKey = 'starter_monthly' | 'starter_yearly' | 'ultra_monthly' | 'ultra_yearly'

const TIER_FEATURES: Record<'free' | 'starter' | 'ultra', string[]> = {
  free: [
    '3 research reports / month',
    '1 portfolio (up to 15 holdings)',
    '1 watchlist (up to 10 items)',
    '3 active price alerts',
  ],
  starter: [
    '10 research reports / month',
    '3 portfolios (up to 50 holdings each)',
    '5 watchlists (up to 25 items each)',
    '25 active price alerts',
    'Telegram + CLI access',
  ],
  ultra: [
    '30 research reports / month',
    'Unlimited portfolios and holdings',
    'Unlimited watchlists and items',
    'Unlimited price alerts',
    'Priority support',
  ],
}

function PlanSection() {
  const api = useApiClient()
  const [loadingPlan, setLoadingPlan] = useState<null | PlanKey | 'portal'>(null)
  const [billingInterval, setBillingInterval] = useState<'monthly' | 'yearly'>('monthly')

  const { data, isLoading } = useQuery({
    queryKey: ['billing-status'],
    queryFn: async () => {
      const res = await api.get('/api/billing/status')
      if (!res.ok) throw new Error('Failed to load billing status')
      return res.json() as Promise<{
        is_pro: boolean
        tier: string
        family: 'free' | 'starter' | 'ultra'
        plan: string | null
        current_period_end: string | null
        cancel_at_period_end: boolean
      }>
    },
  })

  const startCheckout = async (plan: PlanKey) => {
    setLoadingPlan(plan)
    try {
      const res = await api.post('/api/billing/checkout', { plan })
      const json = await res.json()
      if (!res.ok || !json.url) throw new Error(json.error || 'Checkout failed')
      window.location.href = json.url
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Checkout failed')
      setLoadingPlan(null)
    }
  }

  const openPortal = async () => {
    setLoadingPlan('portal')
    try {
      const res = await api.get('/api/billing/portal')
      const json = await res.json()
      if (!res.ok || !json.url) throw new Error(json.error || 'Portal unavailable')
      window.location.href = json.url
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Portal unavailable')
      setLoadingPlan(null)
    }
  }

  if (isLoading) {
    return <div style={{ color: '#a8a29e', fontSize: 13 }}>Loading...</div>
  }

  const cardStyle: React.CSSProperties = {
    background: '#1c1917',
    border: '1px solid #292524',
    borderRadius: 14,
    padding: 24,
    display: 'flex',
    flexDirection: 'column',
    gap: 14,
  }
  const priceStyle: React.CSSProperties = {
    fontFamily: 'Nunito, sans-serif',
    fontSize: 30,
    fontWeight: 700,
    color: '#fafaf9',
  }
  const buyBtnStyle: React.CSSProperties = {
    padding: '11px 18px',
    borderRadius: 100,
    border: 'none',
    background: '#d6d3d1',
    color: '#0c0a09',
    fontSize: 13.5,
    fontWeight: 600,
    cursor: 'pointer',
  }

  if (data?.is_pro) {
    const renews = data.current_period_end
      ? new Date(data.current_period_end).toLocaleDateString()
      : null
    const prettyPlan: Record<string, string> = {
      starter_monthly: 'Starter Monthly',
      starter_yearly: 'Starter Yearly',
      ultra_monthly: 'Ultra Monthly',
      ultra_yearly: 'Ultra Yearly',
    }
    const planLabel = (data.plan && prettyPlan[data.plan]) || 'Starter'
    const currentFeatures = TIER_FEATURES[data.family] || []
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 500, padding: '4px 10px', borderRadius: 100, background: 'rgba(34,197,94,0.08)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.2)' }}>
              <Icon name="check_circle" size={13} filled /> Active
            </span>
            <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 18, fontWeight: 700 }}>{planLabel}</div>
          </div>
          <div style={{ fontSize: 13, color: '#a8a29e' }}>
            {data.cancel_at_period_end
              ? `Cancels on ${renews || 'period end'}.`
              : renews ? `Renews on ${renews}.` : 'Active subscription.'}
          </div>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {currentFeatures.map(f => (
              <li key={f} style={{ fontSize: 13, color: '#d6d3d1', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Icon name="check" size={14} /> {f}
              </li>
            ))}
          </ul>
          <button onClick={openPortal} disabled={loadingPlan === 'portal'} style={{ ...buyBtnStyle, alignSelf: 'flex-start' }}>
            {loadingPlan === 'portal' ? 'Opening...' : 'Manage subscription'}
          </button>
        </div>
      </div>
    )
  }

  const intervalBtn = (iv: 'monthly' | 'yearly', label: string) => (
    <button
      key={iv}
      onClick={() => setBillingInterval(iv)}
      style={{
        padding: '7px 16px',
        borderRadius: 100,
        border: '1px solid #292524',
        background: billingInterval === iv ? '#d6d3d1' : 'transparent',
        color: billingInterval === iv ? '#0c0a09' : '#a8a29e',
        fontSize: 13,
        fontWeight: 600,
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  )

  const starterKey: PlanKey = billingInterval === 'yearly' ? 'starter_yearly' : 'starter_monthly'
  const ultraKey: PlanKey = billingInterval === 'yearly' ? 'ultra_yearly' : 'ultra_monthly'
  const starterPrice = billingInterval === 'yearly' ? '$210' : '$19'
  const starterUnit = billingInterval === 'yearly' ? ' / year' : ' / month'
  const ultraPrice = billingInterval === 'yearly' ? '$520' : '$50'
  const ultraUnit = billingInterval === 'yearly' ? ' / year' : ' / month'

  const featureList = (features: string[]) => (
    <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 7 }}>
      {features.map(f => (
        <li key={f} style={{ fontSize: 13, color: '#d6d3d1', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <Icon name="check" size={14} /> <span>{f}</span>
        </li>
      ))}
    </ul>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <p style={{ fontSize: 13, color: '#a8a29e', margin: 0 }}>
        You are on the Free plan. Upgrade for more research, bigger portfolios, and more alerts.
      </p>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {intervalBtn('monthly', 'Monthly')}
        {intervalBtn('yearly', 'Yearly \u00B7 save up to 13%')}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {/* FREE */}
        <div style={cardStyle}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Free</div>
          <div style={priceStyle}>$0<span style={{ fontSize: 14, color: '#a8a29e', fontWeight: 400 }}> / month</span></div>
          <div style={{ fontSize: 13, color: '#a8a29e' }}>Try the core research and portfolio tools.</div>
          {featureList(TIER_FEATURES.free)}
          <button disabled style={{ ...buyBtnStyle, background: 'transparent', color: '#57534e', border: '1px solid #292524', cursor: 'default' }}>
            Current plan
          </button>
        </div>

        {/* STARTER */}
        <div style={{ ...cardStyle, borderColor: '#d6d3d1' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#d6d3d1', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Starter &middot; Recommended</div>
          <div style={priceStyle}>{starterPrice}<span style={{ fontSize: 14, color: '#a8a29e', fontWeight: 400 }}>{starterUnit}</span></div>
          <div style={{ fontSize: 13, color: '#a8a29e' }}>For active investors tracking a real portfolio.</div>
          {featureList(TIER_FEATURES.starter)}
          <button onClick={() => startCheckout(starterKey)} disabled={loadingPlan !== null} style={buyBtnStyle}>
            {loadingPlan === starterKey ? 'Redirecting...' : `Go Starter ${billingInterval === 'yearly' ? 'Yearly' : 'Monthly'}`}
          </button>
        </div>

        {/* ULTRA */}
        <div style={cardStyle}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Ultra</div>
          <div style={priceStyle}>{ultraPrice}<span style={{ fontSize: 14, color: '#a8a29e', fontWeight: 400 }}>{ultraUnit}</span></div>
          <div style={{ fontSize: 13, color: '#a8a29e' }}>For power users with large portfolios and lots of alerts.</div>
          {featureList(TIER_FEATURES.ultra)}
          <button onClick={() => startCheckout(ultraKey)} disabled={loadingPlan !== null} style={{ ...buyBtnStyle, background: '#fafaf9' }}>
            {loadingPlan === ultraKey ? 'Redirecting...' : `Go Ultra ${billingInterval === 'yearly' ? 'Yearly' : 'Monthly'}`}
          </button>
        </div>
      </div>
    </div>
  )
}
