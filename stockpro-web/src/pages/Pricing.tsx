import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import AppNav from '../components/AppNav'
import { useApiClient } from '../api/client'

type Cadence = 'monthly' | 'yearly'

type PlanInfo = {
  monthly_url: string | null
  yearly_url: string | null
  price_monthly: number
  price_yearly: number
}

type PlansResp = {
  success: boolean
  plans: { starter: PlanInfo; ultra: PlanInfo }
}

const FEATURES = {
  free: ['3 research reports / mo', '1 portfolio', 'Watchlist & alerts (basic)'],
  starter: ['10 research reports / mo', '3 portfolios', '20 watchlist tickers', '15 price alerts'],
  ultra: ['Unlimited reports', 'Unlimited portfolios', 'Unlimited watchlist', 'Unlimited alerts'],
}

export default function Pricing() {
  const api = useApiClient()
  const [cadence, setCadence] = useState<Cadence>('monthly')

  const { data } = useQuery<PlansResp>({
    queryKey: ['billing-plans'],
    queryFn: async () => {
      const res = await api.get('/api/billing/plans')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const res = await api.get('/api/settings')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const currentTier = settings?.profile?.tier || 'free'

  const startCheckout = async (tier: 'starter' | 'ultra') => {
    const res = await api.post('/api/billing/checkout-session', { tier, cadence })
    if (!res.ok) {
      toast.error('Could not start checkout. Plan may not be configured yet.')
      return
    }
    const body = await res.json()
    if (!body?.checkout_url) {
      toast.error('Plan not configured.')
      return
    }
    // Open Whop hosted checkout in a new tab — payment + webhook handles the rest.
    window.open(body.checkout_url, '_blank', 'noopener,noreferrer')
    toast.success('Opening checkout… Your plan will activate once payment completes.')
  }

  return (
    <div style={{ background: '#0c0a09', minHeight: '100vh', color: '#fafaf9' }}>
      <AppNav />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '48px 24px 96px' }}>
        <header style={{ textAlign: 'center', marginBottom: 32 }}>
          <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 38, fontWeight: 700, letterSpacing: '-0.02em' }}>
            Plans &amp; pricing
          </h1>
          <p style={{ fontSize: 15, color: '#a8a29e', marginTop: 8 }}>
            Pick a plan that matches how much you research.
          </p>
        </header>

        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 28 }}>
          <div style={{ display: 'inline-flex', background: '#1c1917', border: '1px solid #292524', borderRadius: 100, padding: 4 }}>
            {(['monthly', 'yearly'] as Cadence[]).map(c => (
              <button
                key={c}
                onClick={() => setCadence(c)}
                style={{
                  padding: '8px 18px',
                  borderRadius: 100,
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 13.5,
                  fontWeight: 500,
                  background: cadence === c ? '#d6d3d1' : 'transparent',
                  color: cadence === c ? '#0c0a09' : '#a8a29e',
                }}
              >
                {c === 'monthly' ? 'Monthly' : 'Yearly (2 months free)'}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
          <PlanCard
            name="Free"
            price={0}
            cadence={cadence}
            features={FEATURES.free}
            current={currentTier === 'free'}
          />
          <PlanCard
            name="Starter"
            price={cadence === 'monthly' ? data?.plans.starter.price_monthly ?? 19 : data?.plans.starter.price_yearly ?? 190}
            cadence={cadence}
            features={FEATURES.starter}
            current={currentTier === 'starter'}
            cta={currentTier === 'starter' ? 'Current plan' : 'Upgrade'}
            disabled={currentTier === 'starter'}
            onClick={() => startCheckout('starter')}
          />
          <PlanCard
            name="Ultra"
            price={cadence === 'monthly' ? data?.plans.ultra.price_monthly ?? 59 : data?.plans.ultra.price_yearly ?? 590}
            cadence={cadence}
            features={FEATURES.ultra}
            current={currentTier === 'ultra'}
            cta={currentTier === 'ultra' ? 'Current plan' : 'Upgrade'}
            disabled={currentTier === 'ultra'}
            highlight
            onClick={() => startCheckout('ultra')}
          />
        </div>

        <p style={{ textAlign: 'center', color: '#a8a29e', fontSize: 12.5, marginTop: 24 }}>
          Checkout opens in a new tab. Your plan activates within seconds of payment.
        </p>
      </main>
    </div>
  )
}

function PlanCard({
  name,
  price,
  cadence,
  features,
  current,
  cta,
  disabled,
  highlight,
  onClick,
}: {
  name: string
  price: number
  cadence: Cadence
  features: string[]
  current?: boolean
  cta?: string
  disabled?: boolean
  highlight?: boolean
  onClick?: () => void
}) {
  return (
    <div style={{
      background: highlight ? 'linear-gradient(180deg, #1c1917, #0c0a09)' : '#1c1917',
      border: `1px solid ${highlight ? '#d6d3d1' : '#292524'}`,
      borderRadius: 18,
      padding: 24,
      display: 'flex',
      flexDirection: 'column',
      gap: 16,
      position: 'relative',
    }}>
      {highlight && (
        <span style={{ position: 'absolute', top: 12, insetInlineEnd: 12, fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 100, background: '#d6d3d1', color: '#0c0a09' }}>
          POPULAR
        </span>
      )}
      <div>
        <div style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 20, fontWeight: 700 }}>{name}</div>
        <div style={{ marginTop: 8 }}>
          <span style={{ fontSize: 36, fontWeight: 700, color: '#fafaf9' }}>${price}</span>
          {price > 0 && <span style={{ fontSize: 13, color: '#a8a29e', marginInlineStart: 6 }}>/{cadence === 'monthly' ? 'mo' : 'yr'}</span>}
        </div>
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {features.map((f, i) => (
          <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5, color: '#d6d3d1' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#22c55e' }}>check</span>
            {f}
          </li>
        ))}
      </ul>
      <button
        disabled={disabled || !onClick}
        onClick={onClick}
        style={{
          marginTop: 'auto',
          padding: '10px 16px',
          borderRadius: 100,
          border: 'none',
          background: current ? '#292524' : highlight ? '#d6d3d1' : '#1c1917',
          color: current ? '#a8a29e' : highlight ? '#0c0a09' : '#fafaf9',
          fontSize: 13.5,
          fontWeight: 600,
          cursor: disabled || !onClick ? 'default' : 'pointer',
          outline: !highlight && !current ? '1px solid #292524' : 'none',
        }}
      >
        {cta || (current ? 'Current plan' : 'Get started')}
      </button>
    </div>
  )
}
