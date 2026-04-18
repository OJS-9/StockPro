import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import AppNav from '../components/AppNav'
import { useApiClient } from '../api/client'

type Status = 'idle' | 'submitting' | 'approved' | 'error'

export default function DevicePage() {
  const api = useApiClient()
  const [params] = useSearchParams()
  const [code, setCode] = useState(() => (params.get('user_code') || '').toUpperCase())
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fromUrl = params.get('user_code')
    if (fromUrl) setCode(fromUrl.toUpperCase())
  }, [params])

  async function approve() {
    setStatus('submitting')
    setError(null)
    const res = await api.post('/api/device/approve', { user_code: code })
    if (res.ok) {
      setStatus('approved')
      return
    }
    const body = await res.json().catch(() => ({}))
    const reason = body.error || 'unknown_error'
    // If already approved, treat as success — the agent already has the token.
    if (reason === 'already_approved') {
      setStatus('approved')
      return
    }
    setError(
      reason === 'unknown_code' || reason === 'invalid_code'
        ? 'That code is not valid. Check the code printed in your terminal.'
        : reason === 'expired'
          ? 'That code has expired. Start a new login from your agent.'
          : res.status >= 500
            ? 'Server is temporarily busy. Please try again in a moment.'
            : 'Something went wrong. Try again.'
    )
    setStatus('error')
  }

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#d6d3d1', fontFamily: 'Inter, sans-serif' }}>
      <AppNav />
      <div
        style={{
          maxWidth: 480,
          margin: '0 auto',
          padding: '64px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 24,
        }}
      >
        <div>
          <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 28, fontWeight: 700, margin: 0 }}>
            Authorize device
          </h1>
          <p style={{ color: '#a8a29e', marginTop: 8, fontSize: 14, lineHeight: 1.5 }}>
            Enter the code shown in your terminal to let that device act on your behalf. Approving
            issues a long-lived CLI token you can revoke later in Settings.
          </p>
        </div>

        {status === 'approved' ? (
          <div
            style={{
              background: '#1c1917',
              border: '1px solid #22c55e',
              borderRadius: 16,
              padding: 24,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 600, color: '#22c55e' }}>Device authorized</div>
            <div style={{ color: '#a8a29e', fontSize: 14 }}>
              You can close this window. The agent terminal should now show "authenticated".
            </div>
          </div>
        ) : (
          <div
            style={{
              background: '#1c1917',
              border: '1px solid #292524',
              borderRadius: 16,
              padding: 24,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
            }}
          >
            <label htmlFor="code" style={{ fontSize: 13, color: '#a8a29e' }}>
              Code from your agent
            </label>
            <input
              id="code"
              value={code}
              onChange={e => setCode(e.target.value.toUpperCase())}
              placeholder="ABCD-1234"
              autoFocus
              autoComplete="off"
              spellCheck={false}
              style={{
                background: '#0c0a09',
                border: '1px solid #292524',
                borderRadius: 10,
                padding: '14px 16px',
                color: '#fafaf9',
                fontFamily: 'ui-monospace, monospace',
                fontSize: 20,
                letterSpacing: 2,
                textAlign: 'center',
              }}
            />
            {error && (
              <div style={{ color: '#ef4444', fontSize: 13 }}>{error}</div>
            )}
            <button
              onClick={approve}
              disabled={status === 'submitting' || code.replace(/[-\s]/g, '').length < 8}
              style={{
                background: '#d6d3d1',
                color: '#0c0a09',
                padding: '12px 16px',
                borderRadius: 999,
                border: 0,
                fontWeight: 600,
                fontSize: 14,
                cursor: status === 'submitting' ? 'progress' : 'pointer',
                opacity: code.replace(/[-\s]/g, '').length < 8 ? 0.5 : 1,
              }}
            >
              {status === 'submitting' ? 'Approving...' : 'Approve device'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
