import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import toast from 'react-hot-toast'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useAuth } from '@clerk/clerk-react'
import { useLanguage } from '../LanguageContext'
import { useBreakpoint } from '../hooks/useBreakpoint'
import { useResearchProgress } from '../ResearchProgressContext'

const TRADE_TYPES = [
  { id: 'day', icon: 'bolt', iconStyle: 'bull', name: 'Day Trade', nameKey: 'research.dayTrade', descKey: 'research.dayTradeDesc' },
  { id: 'swing', icon: 'show_chart', iconStyle: 'neutral', name: 'Swing Trade', nameKey: 'research.swingTrade', descKey: 'research.swingTradeDesc' },
  { id: 'investment', icon: 'library_books', iconStyle: 'full', name: 'Investment', nameKey: 'research.investment', descKey: 'research.investmentDesc' },
]

const POSITION_GOALS: Record<string, string[]> = {
  'Investment': ['DCA into my position', 'Re-evaluate (hold or sell)', 'Assess for initial sizing'],
  'Swing Trade': ['Increase my position', 'Hedge with options or short', 'Start a new leveraged position'],
  'Day Trade': ['Leveraged long play', 'Hedge my position', 'Exit strategy — close today'],
}

const iconBg: Record<string, string> = {
  bull: 'rgba(34,197,94,0.08)',
  neutral: 'rgba(214,211,209,0.08)',
  full: 'rgba(96,165,250,0.08)',
}
const iconColor: Record<string, string> = {
  bull: '#22c55e',
  neutral: '#d6d3d1',
  full: '#60a5fa',
}

type Phase = 'setup' | 'position' | 'loading' | 'subjects' | 'questions'

interface PopupQuestion {
  question: string
  options: string[]
}

interface Subject {
  id: string
  name: string
  description: string
  priority: number
}

interface PopupData {
  questions: PopupQuestion[]
  session_id: string
  subjects: Subject[]
}

export default function ResearchWizard() {
  const [searchParams] = useSearchParams()
  const [ticker, setTicker] = useState(searchParams.get('ticker') || '')
  const [tradeType, setTradeType] = useState<string | null>(null)
  const [tickerInfo, setTickerInfo] = useState<any>(null)
  const [phase, setPhase] = useState<Phase>('setup')
  const { t } = useTranslation()
  const { lang } = useLanguage()
  const { isMobile } = useBreakpoint()
  const fmt = (n: number) => new Intl.NumberFormat(lang === 'he' ? 'he-IL' : 'en-US', { style: 'currency', currency: 'USD' }).format(n)

  // Position pre-screen state
  const [positionData, setPositionData] = useState<any>(null)
  const [positionStep, setPositionStep] = useState<1 | 2>(1)
  const [positionSummary, setPositionSummary] = useState('')

  // Popup data from /popup_start
  const [popupData, setPopupData] = useState<PopupData | null>(null)
  const [selectedSubjectIds, setSelectedSubjectIds] = useState<string[]>([])
  const [answers, setAnswers] = useState<string[]>([])

  const api = useApiClient()
  const { getToken } = useAuth()
  const researchProgress = useResearchProgress()

  const { data: recentData } = useQuery({
    queryKey: ['recent-tickers'],
    queryFn: async () => {
      const res = await api.get('/api/tickers/recent')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const recentTickers = recentData?.tickers || ['NVDA', 'AAPL', 'TSLA', 'BTC']

  useEffect(() => {
    if (!ticker || ticker.length < 1) { setTickerInfo(null); return }
    const timer = setTimeout(async () => {
      try {
        const res = await api.get(`/api/ticker/search?q=${ticker.toUpperCase()}`)
        if (res.ok) setTickerInfo(await res.json())
      } catch {}
    }, 400)
    return () => clearTimeout(timer)
  }, [ticker])

  // Call /popup_start and advance to subjects or questions phase
  const callPopupStart = async (posSummary: string, posGoal: string) => {
    setPhase('loading')
    try {
      const token = await getToken()
      // Always send English name to the API regardless of display language
      const tradeTypeFullForApi = TRADE_TYPES.find(tt => tt.id === tradeType)?.name || tradeType || ''
      const formData = new FormData()
      formData.append('ticker', ticker.toUpperCase())
      formData.append('trade_type', tradeTypeFullForApi)
      formData.append('language', lang)
      if (posSummary) formData.append('position_summary', posSummary)
      if (posGoal) formData.append('position_goal', posGoal)

      const res = await fetch('/popup_start', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to initialize research')
      const data: PopupData = await res.json()
      setPopupData(data)

      if (data.subjects && data.subjects.length > 0) {
        // Pre-select priority-1 subjects
        setSelectedSubjectIds(data.subjects.filter(s => s.priority === 1).map(s => s.id))
        setAnswers(new Array(data.questions.length).fill(''))
        setPhase('subjects')
      } else if (data.questions && data.questions.length > 0) {
        setAnswers(new Array(data.questions.length).fill(''))
        setPhase('questions')
      } else {
        // No subjects, no questions — go straight to generation
        await callStartGeneration(data, [], [])
      }
    } catch (e: any) {
      toast.error(e.message || t('research.toasts.initFailed'))
      setPhase('setup')
    }
  }

  const callStartGeneration = async (data: PopupData, subjectIds: string[], userAnswers: string[]) => {
    try {
      const token = await getToken()
      const res = await fetch('/start_generation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          questions: data.questions.map(q => q.question),
          answers: userAnswers,
          selected_subject_ids: subjectIds.length > 0 ? subjectIds : null,
        }),
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Failed to start research generation')
      researchProgress.start(data.session_id, ticker.toUpperCase())
      setPhase('setup')
      setPopupData(null)
      setSelectedSubjectIds([])
      setAnswers([])
      toast.success(t('research.toasts.started'))
    } catch (e: any) {
      toast.error(e.message || t('research.toasts.startFailed'))
      setPhase('setup')
    }
  }

  // Launch button clicked — check position first
  const launchMutation = useMutation({
    mutationFn: async () => {
      const res = await api.get(`/api/position_check/${ticker.toUpperCase()}`)
      if (!res.ok) return { holding: false, positions: [] }
      return res.json()
    },
    onSuccess: (data) => {
      if (data.holding && data.positions?.length > 0) {
        setPositionData(data.positions)
        setPositionStep(1)
        setPhase('position')
      } else {
        callPopupStart('', '')
      }
    },
    onError: () => callPopupStart('', ''),
  })

  const canLaunch = ticker.trim() && tradeType

  const step = !ticker.trim() ? 1 : !tradeType ? 2 : 3

  const tradeTypeEntry = TRADE_TYPES.find(tt => tt.id === tradeType)
  const tradeTypeFull = tradeTypeEntry ? t(tradeTypeEntry.nameKey) : 'Investment'
  const goalOptions = POSITION_GOALS[tradeTypeEntry?.name || 'Investment'] || POSITION_GOALS['Investment']

  const isModalOpen = phase === 'position' || phase === 'loading' || phase === 'subjects' || phase === 'questions'

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 800, margin: '0 auto', padding: isMobile ? '28px 16px 60px' : '56px 48px 80px' }}>

        {/* STEP INDICATOR */}
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 48 }}>
          {[
            { n: 1, label: t('research.step1') },
            { n: 2, label: t('research.step2') },
            { n: 3, label: t('research.step3') },
          ].map(({ n, label }, i) => {
            const done = step > n
            const active = step === n
            return (
              <div key={n} style={{ display: 'flex', alignItems: 'center', flex: i < 2 ? 1 : 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 32, height: 32, borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 600, fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', background: done ? '#22c55e' : active ? '#d6d3d1' : '#1c1917', color: done ? '#0c0a09' : active ? '#0c0a09' : '#a8a29e', border: done || active ? 'none' : '1px solid #292524' }}>
                    {done ? <Icon name="check" size={16} filled /> : n}
                  </div>
                  <span style={{ fontSize: 12.5, fontWeight: 500, color: active || done ? '#fafaf9' : '#a8a29e' }}>{label}</span>
                </div>
                {i < 2 && <div style={{ flex: 1, height: 1, background: done ? '#22c55e' : '#292524', margin: '0 12px' }} />}
              </div>
            )
          })}
        </div>

        {/* STEP 1: TICKER */}
        <div style={{ marginBottom: 40 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#a8a29e', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="search" size={14} />
            {t('research.step1Label')}
          </div>
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, display: 'flex', alignItems: 'center', gap: 12, padding: '0 20px', height: 60, marginBottom: 16 }}>
            <Icon name="query_stats" size={22} />
            <input
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              placeholder={t('research.enterTicker')}
              style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 20, fontWeight: 600, color: '#fafaf9', letterSpacing: '0.02em' }}
            />
            {tickerInfo && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0, padding: '6px 14px', background: '#232120', border: '1px solid #292524', borderRadius: 8, fontSize: 13 }}>
                <span style={{ fontWeight: 600, color: '#d6d3d1' }}>{tickerInfo.symbol}</span>
                <span style={{ color: '#a8a29e' }}>{tickerInfo.name}</span>
                {tickerInfo.price && <span style={{ fontVariantNumeric: 'tabular-nums' }}>${tickerInfo.price}</span>}
                {tickerInfo.change_pct !== undefined && (
                  <span style={{ color: tickerInfo.change_pct >= 0 ? '#22c55e' : '#ef4444' }}>
                    <bdi>{tickerInfo.change_pct >= 0 ? '+' : ''}{tickerInfo.change_pct}%</bdi>
                  </span>
                )}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: '#a8a29e' }}>{t('research.recent')}</span>
            {recentTickers.map((tt: string) => (
              <button key={tt} onClick={() => setTicker(tt)} style={{ padding: '4px 12px', borderRadius: 999, fontSize: 12.5, fontWeight: 600, border: '1px solid #292524', background: ticker === tt ? '#232120' : '#1c1917', color: ticker === tt ? '#fafaf9' : '#a8a29e', cursor: 'pointer', fontFamily: 'Nunito, "Secular One", Heebo, sans-serif' }}>
                {tt}
              </button>
            ))}
          </div>
        </div>

        {/* STEP 2: TRADE TYPE */}
        <div style={{ marginBottom: 40, opacity: !ticker.trim() ? 0.5 : 1, pointerEvents: !ticker.trim() ? 'none' : 'auto' }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#a8a29e', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icon name="psychology" size={14} />
            {t('research.step2Label')}
          </div>
          <h2 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: isMobile ? 20 : 28, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 8 }}>{t('research.whatsYourTradeType')}</h2>
          <p style={{ fontSize: 14, color: '#a8a29e', marginBottom: 28 }}>{t('research.tradeTypeDesc')}</p>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: 12 }}>
            {TRADE_TYPES.map(({ id, icon, iconStyle, nameKey, descKey }) => (
              <div key={id} onClick={() => setTradeType(id)} style={{ background: '#1c1917', border: `2px solid ${tradeType === id ? '#d6d3d1' : '#292524'}`, borderRadius: 14, padding: 20, cursor: 'pointer', position: 'relative' }}>
                {tradeType === id && (
                  <div style={{ position: 'absolute', top: 12, insetInlineEnd: 12, width: 18, height: 18, borderRadius: '50%', background: '#d6d3d1', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Icon name="check" size={12} filled />
                  </div>
                )}
                <div style={{ width: 40, height: 40, borderRadius: 10, marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', background: iconBg[iconStyle] }}>
                  <span style={{ color: iconColor[iconStyle] }}><Icon name={icon} size={22} /></span>
                </div>
                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{t(nameKey)}</div>
                <div style={{ fontSize: 12.5, color: '#a8a29e', lineHeight: 1.55 }}>{t(descKey)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* LAUNCH */}
        <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: isMobile ? 20 : 28, display: 'flex', alignItems: isMobile ? 'stretch' : 'center', justifyContent: 'space-between', gap: isMobile ? 14 : 20, opacity: canLaunch ? 1 : 0.5, flexDirection: isMobile ? 'column' : 'row' }}>
          <div>
            <h3 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 18, fontWeight: 600, marginBottom: 6 }}>
              {canLaunch ? t('research.readyToResearch', { ticker }) : t('research.completeSteps')}
            </h3>
            <p style={{ fontSize: 13, color: '#a8a29e', lineHeight: 1.5 }}>
              {tradeType ? tradeTypeFull : t('research.selectTradeType')} &middot; {t('research.fullPipeline')}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#a8a29e', marginTop: 10 }}>
              <Icon name="schedule" size={15} />
              {t('research.estimatedTime')}
            </div>
          </div>
          <button
            onClick={() => canLaunch && phase === 'setup' && !launchMutation.isPending && launchMutation.mutate()}
            disabled={!canLaunch || launchMutation.isPending || phase !== 'setup'}
            style={{ background: canLaunch && phase === 'setup' ? '#d6d3d1' : '#292524', color: canLaunch && phase === 'setup' ? '#0c0a09' : '#a8a29e', fontSize: 15, fontWeight: 700, padding: '14px 28px', borderRadius: 10, border: 'none', cursor: canLaunch && phase === 'setup' ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap', fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', flexShrink: 0 }}
          >
            <Icon name="auto_awesome" size={20} filled />
            {launchMutation.isPending ? t('research.checking') : t('research.launchResearch')}
          </button>
        </div>
      </main>

      {/* ── MODAL OVERLAY ── */}
      {isModalOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>

          {/* LOADING */}
          {phase === 'loading' && (
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 18, padding: '48px 36px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(214,211,209,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Icon name="autorenew" size={24} />
              </div>
              <div style={{ fontSize: 15, fontWeight: 600 }}>{t('research.preparingSession')}</div>
              <div style={{ fontSize: 13, color: '#a8a29e' }}>{t('research.fewSeconds')}</div>
            </div>
          )}

          {/* POSITION PRE-SCREEN */}
          {phase === 'position' && positionData && (
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 18, padding: 32, maxWidth: 480, width: '100%', boxShadow: '0 24px 60px rgba(0,0,0,0.6)' }}>
              {positionStep === 1 ? (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(214,211,209,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Icon name="account_balance_wallet" size={20} />
                    </div>
                    <div>
                      <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 16, fontWeight: 700 }}>
                        {t('research.youHold')} <span style={{ fontFamily: 'monospace' }}>{ticker}</span>
                      </div>
                      <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 2 }}>{t('research.includePosition')}</div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
                    {positionData.map((p: any, i: number) => (
                      <div key={i} style={{ background: '#232120', border: '1px solid #292524', borderRadius: 10, padding: '12px 14px' }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{p.portfolio_name}</div>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>
                          {p.quantity % 1 === 0 ? p.quantity.toLocaleString() : p.quantity.toFixed(4)} shares at {fmt(p.average_cost)} avg cost
                        </div>
                        <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 2 }}>{fmt(p.total_cost_basis)} total cost basis</div>
                      </div>
                    ))}
                  </div>

                  <div style={{ display: 'flex', gap: 10 }}>
                    <button
                      onClick={() => {
                        const summary = positionData.map((p: any) =>
                          `Portfolio "${p.portfolio_name}": ${p.quantity} shares at $${p.average_cost.toFixed(2)} avg cost ($${p.total_cost_basis.toFixed(2)} total cost basis)`
                        ).join('; ')
                        setPositionSummary(summary)
                        setPositionStep(2)
                      }}
                      style={{ flex: 2, padding: '12px', borderRadius: 10, border: 'none', background: '#d6d3d1', color: '#0c0a09', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'Nunito, "Secular One", Heebo, sans-serif' }}
                    >
                      {t('research.yesConsider')}
                    </button>
                    <button
                      onClick={() => callPopupStart('', '')}
                      style={{ flex: 1, padding: '12px', borderRadius: 10, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}
                    >
                      {t('research.skip')}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: 'rgba(214,211,209,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Icon name="flag" size={20} />
                    </div>
                    <div>
                      <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 16, fontWeight: 700 }}>{t('research.whatsYourGoal')}</div>
                      <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 2 }}>{t('research.goalDesc')}</div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
                    {goalOptions.map((goal) => (
                      <button
                        key={goal}
                        onClick={() => callPopupStart(positionSummary, goal)}
                        style={{ display: 'block', width: '100%', textAlign: 'start', padding: '12px 16px', borderRadius: 10, border: '1px solid #292524', background: 'transparent', color: '#fafaf9', fontSize: 13, fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s' }}
                      >
                        {goal}
                      </button>
                    ))}
                  </div>

                  <button
                    onClick={() => setPositionStep(1)}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', border: 'none', color: '#a8a29e', fontSize: 13, cursor: 'pointer', padding: 0 }}
                  >
                    <Icon name="arrow_back" size={15} /> {t('research.back')}
                  </button>
                </>
              )}
            </div>
          )}

          {/* SUBJECTS — Step 1 of 2 */}
          {phase === 'subjects' && popupData && (
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 18, padding: 32, maxWidth: 540, width: '100%', boxShadow: '0 24px 60px rgba(0,0,0,0.6)', maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 17, fontWeight: 700 }}>{t('research.selectTopics')}</div>
                <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#a8a29e' }}>Step 1 of 2</span>
              </div>
              <div style={{ fontSize: 12, color: '#a8a29e', marginBottom: 16 }}>{t('research.chooseAreas')}</div>

              <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, paddingInlineEnd: 4, marginBottom: 16 }}>
                {popupData.subjects.map((s) => {
                  const checked = selectedSubjectIds.includes(s.id)
                  return (
                    <label key={s.id} onClick={() => setSelectedSubjectIds(prev => checked ? prev.filter(id => id !== s.id) : [...prev, s.id])} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer', padding: '10px 12px', borderRadius: 10, border: `1px solid ${checked ? 'rgba(214,211,209,0.25)' : '#292524'}`, background: checked ? 'rgba(214,211,209,0.04)' : 'transparent', transition: 'all 0.15s' }}>
                      <div style={{ width: 18, height: 18, borderRadius: 4, border: `2px solid ${checked ? '#d6d3d1' : '#57534e'}`, background: checked ? '#d6d3d1' : 'transparent', flexShrink: 0, marginTop: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {checked && <Icon name="check" size={12} />}
                      </div>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: checked ? '#fafaf9' : '#d6d3d1', marginBottom: 2 }}>{t(`subject.${s.id}`, s.name)}</div>
                        <div style={{ fontSize: 12, color: '#a8a29e', lineHeight: 1.4 }}>{t(`subject.${s.id}.desc`, s.description)}</div>
                      </div>
                    </label>
                  )
                })}
              </div>

              <div style={{ borderTop: '1px solid #292524', paddingTop: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', gap: 16 }}>
                  <button onClick={() => setSelectedSubjectIds(popupData.subjects.map(s => s.id))} style={{ background: 'none', border: 'none', color: '#a8a29e', fontSize: 13, cursor: 'pointer', padding: 0 }}>
                    {t('research.selectAll')}
                  </button>
                  <button onClick={() => setSelectedSubjectIds([])} style={{ background: 'none', border: 'none', color: '#a8a29e', fontSize: 13, cursor: 'pointer', padding: 0 }}>
                    {t('research.deselectAll')}
                  </button>
                  <button onClick={() => { setSelectedSubjectIds([]); setPhase('questions') }} style={{ background: 'none', border: 'none', color: '#a8a29e', fontSize: 13, cursor: 'pointer', padding: 0 }}>
                    {t('research.skip')}
                  </button>
                </div>
                <button
                  onClick={() => {
                    if (popupData.questions.length > 0) {
                      setPhase('questions')
                    } else {
                      callStartGeneration(popupData, selectedSubjectIds, answers)
                    }
                  }}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 20px', borderRadius: 10, border: 'none', background: '#d6d3d1', color: '#0c0a09', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'Nunito, "Secular One", Heebo, sans-serif' }}
                >
                  {t('research.next')} <Icon name="arrow_forward" size={16} />
                </button>
              </div>
            </div>
          )}

          {/* QUESTIONS — Step 2 of 2 */}
          {phase === 'questions' && popupData && (
            <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 18, padding: 32, maxWidth: 540, width: '100%', boxShadow: '0 24px 60px rgba(0,0,0,0.6)', maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 34, height: 34, borderRadius: 9, background: 'rgba(214,211,209,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Icon name="psychology" size={18} />
                  </div>
                  <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 17, fontWeight: 700 }}>{t('research.quickQuestions')}</div>
                </div>
                {popupData.subjects.length > 0 && (
                  <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#a8a29e' }}>Step 2 of 2</span>
                )}
              </div>
              <div style={{ fontSize: 12, color: '#a8a29e', marginBottom: 20 }}>{t('research.helpAiTailor', { ticker })}</div>

              <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 22, marginBottom: 16, paddingInlineEnd: 4 }}>
                {popupData.questions.map((q, qi) => (
                  <div key={qi}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 10, lineHeight: 1.4 }}>{q.question}</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                      {q.options.map((opt, oi) => {
                        const selected = answers[qi] === opt
                        return (
                          <button
                            key={oi}
                            onClick={() => {
                              const next = [...answers]
                              next[qi] = opt
                              setAnswers(next)
                            }}
                            style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderRadius: 10, border: `1px solid ${selected ? '#d6d3d1' : '#292524'}`, background: selected ? 'rgba(214,211,209,0.06)' : 'transparent', color: selected ? '#fafaf9' : '#a8a29e', fontSize: 13, cursor: 'pointer', textAlign: 'start', transition: 'all 0.15s' }}
                          >
                            <div style={{ width: 16, height: 16, borderRadius: '50%', border: `2px solid ${selected ? '#d6d3d1' : '#57534e'}`, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              {selected && <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#d6d3d1' }} />}
                            </div>
                            {opt}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ borderTop: '1px solid #292524', paddingTop: 16, display: 'flex', gap: 10 }}>
                <button
                  onClick={() => {
                    if (popupData.subjects.length > 0) {
                      setPhase('subjects')
                    } else {
                      setPhase('setup')
                      setPopupData(null)
                      setAnswers([])
                    }
                  }}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', border: '1px solid #292524', color: '#a8a29e', fontSize: 13, cursor: 'pointer', padding: '10px 16px', borderRadius: 10 }}
                >
                  <Icon name="arrow_back" size={15} /> {t('research.back')}
                </button>
                <button
                  onClick={() => callStartGeneration(popupData, selectedSubjectIds, answers)}
                  style={{ flex: 1, padding: '11px', borderRadius: 10, border: 'none', background: '#d6d3d1', color: '#0c0a09', fontSize: 14, fontWeight: 700, cursor: 'pointer', fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
                >
                  <Icon name="auto_awesome" size={18} filled />
                  {t('research.generateReport')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
