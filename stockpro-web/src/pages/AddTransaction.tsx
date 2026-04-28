import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router'
import toast from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import AppNav from '../components/AppNav'
import Icon from '../components/Icon'
import { useApiClient } from '../api/client'
import { useBreakpoint } from '../hooks/useBreakpoint'

const fmt = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)

export default function AddTransaction() {
  const { id } = useParams()
  const navigate = useNavigate()
  const api = useApiClient()
  const { isMobile } = useBreakpoint()
  const { t } = useTranslation()
  const [form, setForm] = useState({ symbol: '', type: 'BUY', shares: '', price: '', date: new Date().toISOString().split('T')[0] })

  const total = parseFloat(form.shares || '0') * parseFloat(form.price || '0')

  const mutation = useMutation({
    mutationFn: async () => {
      const res = await api.post(`/api/portfolio/${id}/transaction`, {
        symbol: form.symbol.toUpperCase(),
        type: form.type,
        shares: parseFloat(form.shares),
        price: parseFloat(form.price),
        date: form.date,
      })
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
    onSuccess: () => {
      toast.success(t('transactions.toasts.added'))
      navigate(`/portfolio/${id}`)
    },
    onError: () => toast.error(t('transactions.toasts.addFailed')),
  })

  const inputStyle = {
    width: '100%',
    background: '#1c1917',
    border: '1px solid #292524',
    borderRadius: 10,
    padding: '12px 14px',
    color: '#fafaf9',
    fontFamily: 'Inter, Heebo, sans-serif',
    fontSize: 14,
    outline: 'none',
    boxSizing: 'border-box' as const,
  }

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 640, margin: '0 auto', padding: isMobile ? '24px 16px 60px' : '48px 48px 80px' }}>

        {/* HEADER */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Link to={`/portfolio/${id}`} style={{ color: '#a8a29e', textDecoration: 'none', fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Icon name="arrow_back" size={16} /> Portfolio
            </Link>
          </div>
          <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 26, fontWeight: 600, letterSpacing: '-0.02em' }}>Add Transaction</h1>
        </div>

        <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 16, padding: isMobile ? 20 : 32, marginBottom: 20 }}>
          {/* BUY / SELL TOGGLE */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 24, padding: 4, background: '#232120', borderRadius: 10 }}>
            {['BUY', 'SELL'].map(t => (
              <button
                key={t}
                onClick={() => setForm(f => ({ ...f, type: t }))}
                style={{ flex: 1, padding: '9px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, background: form.type === t ? (t === 'BUY' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)') : 'transparent', color: form.type === t ? (t === 'BUY' ? '#22c55e' : '#ef4444') : '#a8a29e', transition: 'all 0.15s' }}
              >
                {t}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#a8a29e', marginBottom: 6, letterSpacing: '0.02em' }}>Ticker symbol</label>
              <input
                value={form.symbol}
                onChange={e => setForm(f => ({ ...f, symbol: e.target.value.toUpperCase() }))}
                placeholder="NVDA"
                style={{ ...inputStyle, fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 18, fontWeight: 700, letterSpacing: '0.02em' }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#a8a29e', marginBottom: 6 }}>Number of shares</label>
                <input type="number" value={form.shares} onChange={e => setForm(f => ({ ...f, shares: e.target.value }))} placeholder="0" min="0" step="0.0001" style={inputStyle} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#a8a29e', marginBottom: 6 }}>Price per share ($)</label>
                <input type="number" value={form.price} onChange={e => setForm(f => ({ ...f, price: e.target.value }))} placeholder="0.00" min="0" step="0.01" style={inputStyle} />
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#a8a29e', marginBottom: 6 }}>Transaction date</label>
              <input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} style={inputStyle} />
            </div>
          </div>
        </div>

        {/* PREVIEW */}
        {total > 0 && (
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 14, padding: '20px 24px', marginBottom: 20 }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#a8a29e', marginBottom: 16 }}>Transaction Preview</div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600 }}>{form.type} {form.symbol || 'TICKER'}</div>
                <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 2 }}>
                  {form.shares} shares @ {form.price ? `$${parseFloat(form.price).toFixed(2)}` : '$0.00'} each
                </div>
              </div>
              <div style={{ textAlign: 'end' }}>
                <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 22, fontWeight: 600 }}>{fmt(total)}</div>
                <div style={{ fontSize: 11, color: '#a8a29e', marginTop: 2 }}>Total {form.type === 'BUY' ? 'cost' : 'proceeds'}</div>
              </div>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 10 }}>
          <Link to={`/portfolio/${id}`} style={{ flex: 1, padding: '12px', borderRadius: 10, border: '1px solid #292524', background: 'transparent', color: '#a8a29e', fontSize: 14, fontWeight: 500, cursor: 'pointer', textAlign: 'center', textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            Cancel
          </Link>
          <button
            onClick={() => mutation.mutate()}
            disabled={!form.symbol || !form.shares || !form.price || mutation.isPending}
            style={{ flex: 2, padding: '12px', borderRadius: 10, border: 'none', background: form.symbol && form.shares && form.price ? '#d6d3d1' : '#292524', color: form.symbol && form.shares && form.price ? '#0c0a09' : '#a8a29e', fontSize: 14, fontWeight: 600, cursor: form.symbol && form.shares && form.price ? 'pointer' : 'not-allowed' }}
          >
            {mutation.isPending ? 'Adding...' : `Add ${form.type} Transaction`}
          </button>
        </div>
      </main>
    </div>
  )
}
