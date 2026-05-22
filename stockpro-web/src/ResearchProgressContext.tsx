import { createContext, useContext, useState, useRef, useEffect, useCallback, type ReactNode } from 'react'
import { useAuth } from '@clerk/clerk-react'

type Status = 'idle' | 'generating' | 'ready' | 'error'

interface Ctx {
  status: Status
  progress: number
  step: string
  stepCode: string
  done: number | null
  total: number | null
  ticker: string
  sessionId: string | null
  reportId: string | null
  start: (sessionId: string, ticker: string) => void
  dismiss: () => void
}

const ResearchProgressContext = createContext<Ctx | null>(null)

export function useResearchProgress() {
  const ctx = useContext(ResearchProgressContext)
  if (!ctx) throw new Error('useResearchProgress must be used inside ResearchProgressProvider')
  return ctx
}

export function ResearchProgressProvider({ children }: { children: ReactNode }) {
  const { getToken } = useAuth()
  const [status, setStatus] = useState<Status>('idle')
  const [progress, setProgress] = useState(0)
  const [step, setStep] = useState('')
  const [stepCode, setStepCode] = useState('')
  const [done, setDone] = useState<number | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [ticker, setTicker] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [reportId, setReportId] = useState<string | null>(null)

  const timerRef = useRef<number | null>(null)
  const activeRef = useRef(false)

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  const dismiss = useCallback(() => {
    activeRef.current = false
    clearTimer()
    setStatus('idle')
    setProgress(0)
    setStep('')
    setStepCode('')
    setDone(null)
    setTotal(null)
    setTicker('')
    setSessionId(null)
    setReportId(null)
  }, [])

  const poll = useCallback(async (sid: string) => {
    if (!activeRef.current) return
    try {
      const token = await getToken()
      const r = await fetch(`/api/report_status/${sid}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: 'include',
      })
      if (!activeRef.current) return
      if (!r.ok) {
        timerRef.current = window.setTimeout(() => poll(sid), 3000)
        return
      }
      const s = await r.json()
      if (!activeRef.current) return
      if (s.status === 'ready' && s.report_id) {
        setStatus('ready')
        setProgress(100)
        setStep('')
        setStepCode('ready')
        setReportId(s.report_id)
        activeRef.current = false
      } else if (s.status === 'error') {
        setStatus('error')
        setStep(s.step || 'Research failed')
        setStepCode('error')
        activeRef.current = false
      } else {
        if (typeof s.progress === 'number') setProgress(s.progress)
        if (typeof s.step === 'string') setStep(s.step)
        if (typeof s.step_code === 'string') setStepCode(s.step_code)
        if (typeof s.done === 'number') setDone(s.done)
        if (typeof s.total === 'number') setTotal(s.total)
        timerRef.current = window.setTimeout(() => poll(sid), 3000)
      }
    } catch {
      if (activeRef.current) {
        timerRef.current = window.setTimeout(() => poll(sid), 5000)
      }
    }
  }, [getToken])

  const start = useCallback((sid: string, tkr: string) => {
    clearTimer()
    activeRef.current = true
    setSessionId(sid)
    setTicker(tkr)
    setStatus('generating')
    setProgress(5)
    setStep('')
    setStepCode('starting')
    setDone(null)
    setTotal(null)
    setReportId(null)
    timerRef.current = window.setTimeout(() => poll(sid), 3000)
  }, [poll])

  useEffect(() => () => {
    activeRef.current = false
    clearTimer()
  }, [])

  return (
    <ResearchProgressContext.Provider value={{ status, progress, step, stepCode, done, total, ticker, sessionId, reportId, start, dismiss }}>
      {children}
    </ResearchProgressContext.Provider>
  )
}
