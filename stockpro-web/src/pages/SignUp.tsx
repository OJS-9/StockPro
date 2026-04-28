import { SignUp as ClerkSignUp } from '@clerk/clerk-react'
import { Link } from 'react-router'
import { Trans, useTranslation } from 'react-i18next'
import Icon from '../components/Icon'
import { useBreakpoint } from '../hooks/useBreakpoint'

export default function SignUp() {
  const { isMobile } = useBreakpoint()
  const { t } = useTranslation()
  return (
    <div style={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>
      {/* Left branding panel */}
      {!isMobile && (
      <div
        style={{
          background: '#1c1917',
          borderInlineEnd: '1px solid #292524',
          padding: 48,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: -120,
            insetInlineEnd: -120,
            width: 440,
            height: 440,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(34,197,94,0.07) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />
        <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 20, fontWeight: 700, color: '#d6d3d1', letterSpacing: '-0.02em' }}>
          StockPro
        </div>

        <div style={{ position: 'relative', zIndex: 1 }}>
          <h2
            style={{
              fontFamily: 'Nunito, sans-serif',
              fontSize: 38,
              fontWeight: 600,
              lineHeight: 1.15,
              letterSpacing: '-0.03em',
              marginBottom: 20,
            }}
          >
            Start researching smarter{' '}
            <em style={{ fontStyle: 'normal', color: '#22c55e' }}>today</em>
          </h2>
          <p style={{ fontSize: 15, color: '#a8a29e', lineHeight: 1.75, maxWidth: 380 }}>
            Free tier available. No credit card required. Get access to AI-powered research, portfolio tracking, and price alerts instantly.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 36 }}>
            {[
              { icon: 'auto_awesome', text: 'Deep AI research reports in minutes' },
              { icon: 'pie_chart', text: 'Portfolio tracking with real P&L analytics' },
              { icon: 'notifications_active', text: 'Instant price alerts via Telegram' },
              { icon: 'visibility', text: 'Watchlists with earnings calendar' },
            ].map(({ icon, text }) => (
              <div key={text} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 14, color: 'rgba(250,250,249,0.65)' }}>
                <Icon name={icon} filled size={18} />
                {text}
              </div>
            ))}
          </div>
        </div>

        <div style={{ fontSize: 12, color: '#a8a29e' }}>&copy; 2026 StockPro. Built for retail investors.</div>
      </div>
      )}

      {/* Right auth panel */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, padding: isMobile ? '24px 16px' : 48, background: isMobile ? '#1c1917' : undefined }}>
        <ClerkSignUp
          routing="path"
          path={`${import.meta.env.BASE_URL}sign-up`}
          signInUrl={`${import.meta.env.BASE_URL}sign-in`}
          afterSignUpUrl={`${import.meta.env.BASE_URL}home`}
          appearance={{
            variables: {
              colorBackground: '#1c1917',
              colorInputBackground: '#292524',
              colorInputText: '#fafaf9',
              colorText: '#fafaf9',
              colorTextSecondary: '#a8a29e',
              colorPrimary: '#d6d3d1',
              colorDanger: '#ef4444',
              borderRadius: '10px',
              fontFamily: 'Inter, sans-serif',
            },
            elements: {
              card: { border: 'none', boxShadow: 'none', background: 'transparent' },
              headerTitle: { fontFamily: 'Nunito, sans-serif', fontWeight: 600 },
              formButtonPrimary: { background: '#d6d3d1', color: '#0c0a09', fontWeight: 600 },
              socialButtonsBlockButton: {
                background: '#292524',
                border: '1px solid #44403c',
                color: '#fafaf9',
              },
              socialButtonsBlockButtonText: {
                color: '#fafaf9',
              },
              formFieldInput: {
                border: '1px solid #44403c',
                background: '#292524',
                color: '#fafaf9',
              },
              footerActionLink: {
                color: '#d6d3d1',
              },
              footerActionText: {
                color: '#a8a29e',
              },
              dividerLine: {
                background: '#44403c',
              },
              dividerText: {
                color: '#a8a29e',
              },
            },
          }}
        />
        <p style={{ fontSize: 12, color: '#a8a29e', maxWidth: 360, textAlign: 'center', lineHeight: 1.6, margin: 0 }}>
          <Trans
            i18nKey="legal.signupAgreement"
            t={t}
            components={{
              terms: <Link to="/legal/terms" style={{ color: '#d6d3d1', textDecoration: 'underline' }} />,
              privacy: <Link to="/legal/privacy" style={{ color: '#d6d3d1', textDecoration: 'underline' }} />,
            }}
          />
        </p>
      </div>
    </div>
  )
}
