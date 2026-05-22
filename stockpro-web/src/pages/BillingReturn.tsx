import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { useApiClient } from '../api/client'

const POLL_INTERVAL_MS = 2000
const MAX_ATTEMPTS = 15

export default function BillingReturn() {
  const api = useApiClient()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const startingTier = useRef<string>(
    (queryClient.getQueryData<any>(['settings'])?.profile?.tier) || 'free'
  )
  const [timedOut, setTimedOut] = useState(false)
  const [pollKey, setPollKey] = useState(0)

  useEffect(() => {
    let attempts = 0
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const tick = async () => {
      if (cancelled) return
      attempts += 1
      try {
        const res = await api.get('/api/settings')
        if (res.ok) {
          const body = await res.json()
          const newTier = body?.profile?.tier || 'free'
          if (newTier !== startingTier.current && newTier !== 'free') {
            queryClient.setQueryData(['settings'], body)
            const label = newTier.charAt(0).toUpperCase() + newTier.slice(1)
            toast.success(`Welcome to ${label}! Your new quotas are active.`)
            navigate('/settings?upgraded=1', { replace: true })
            return
          }
        }
      } catch {
        // ignore — retry
      }
      if (attempts >= MAX_ATTEMPTS) {
        setTimedOut(true)
        return
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS)
    }

    setTimedOut(false)
    timer = setTimeout(tick, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [pollKey, api, navigate, queryClient])

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 18, padding: 36, maxWidth: 460, width: '100%', textAlign: 'center' }}>
        {!timedOut ? (
          <>
            <div style={{ width: 36, height: 36, border: '3px solid #292524', borderTopColor: '#d6d3d1', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 18px' }} />
            <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
              Activating your subscription…
            </h1>
            <p style={{ fontSize: 14, color: '#a8a29e' }}>
              Hang tight — we're confirming your payment with Whop. This usually takes a few seconds.
            </p>
          </>
        ) : (
          <>
            <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#292524', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 18px' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 24, color: '#d6d3d1' }}>schedule</span>
            </div>
            <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 22, fontWeight: 700, marginBottom: 8 }}>
              Payment received
            </h1>
            <p style={{ fontSize: 14, color: '#a8a29e', marginBottom: 24 }}>
              Your account will update within a minute. You can refresh now or head back to the dashboard — we'll catch up automatically.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button
                onClick={() => setPollKey(k => k + 1)}
                style={{ padding: '10px 18px', borderRadius: 100, border: 'none', background: '#d6d3d1', color: '#0c0a09', fontSize: 13.5, fontWeight: 600, cursor: 'pointer' }}
              >
                Refresh
              </button>
              <button
                onClick={() => navigate('/home')}
                style={{ padding: '10px 18px', borderRadius: 100, background: '#0c0a09', color: '#fafaf9', fontSize: 13.5, fontWeight: 500, border: '1px solid #292524', cursor: 'pointer' }}
              >
                Back to dashboard
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
