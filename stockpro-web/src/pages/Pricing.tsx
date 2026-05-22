import { useQuery } from '@tanstack/react-query'
import AppNav from '../components/AppNav'
import PricingPlans from '../components/PricingPlans'
import { useApiClient } from '../api/client'

export default function Pricing() {
  const api = useApiClient()

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const res = await api.get('/api/settings')
      if (!res.ok) throw new Error('Failed')
      return res.json()
    },
  })

  const currentTier = settings?.profile?.tier || 'free'

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

        <PricingPlans currentTier={currentTier} />
      </main>
    </div>
  )
}
