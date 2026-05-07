import { type ReactNode } from 'react'
import { Link } from 'react-router'
import { useTranslation } from 'react-i18next'
import toast from 'react-hot-toast'
import { useLanguage } from '../../LanguageContext'

function copyEmail(email: string, t: (key: string) => string) {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(email).then(
      () => toast.success(t('legal.emailCopied')),
      () => toast(email)
    )
  } else {
    toast(email)
  }
}

function EmailLink({ email, color = '#22c55e' }: { email: string; color?: string }) {
  const { t } = useTranslation()
  return (
    <a
      href={`mailto:${email}`}
      onClick={(e) => {
        e.preventDefault()
        copyEmail(email, t)
      }}
      style={{ color, textDecoration: 'underline', cursor: 'pointer' }}
      title={t('legal.clickToCopy')}
    >
      {email}
    </a>
  )
}

interface Section {
  title: string
  body: string
}

const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/

function linkifyEmails(text: string): ReactNode[] {
  const parts = text.split(/([\w.+-]+@[\w-]+\.[\w.-]+)/)
  return parts.map((part, idx) =>
    EMAIL_RE.test(part)
      ? <EmailLink key={idx} email={part} />
      : <span key={idx}>{part}</span>
  )
}

interface LegalLayoutProps {
  title: string
  lastUpdated: string
  intro?: string
  disclaimer?: string
  sections: Section[]
  contactEmail: string
  children?: ReactNode
}

export default function LegalLayout({ title, lastUpdated, intro, disclaimer, sections, contactEmail, children }: LegalLayoutProps) {
  const { t } = useTranslation()
  const { dir } = useLanguage()

  return (
    <div dir={dir} style={{ minHeight: '100vh', background: '#0c0a09', color: '#fafaf9', fontFamily: 'Inter, Heebo, sans-serif' }}>
      {/* NAV */}
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 64px',
          height: 64,
          position: 'sticky',
          top: 0,
          zIndex: 100,
          background: 'rgba(12,10,9,0.9)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(41,37,36,0.6)',
        }}
      >
        <Link to="/" style={{ textDecoration: 'none' }}>
          <span style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 18, fontWeight: 700, color: '#d6d3d1', letterSpacing: '-0.02em' }}>
            StockPro
          </span>
        </Link>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Link to="/sign-in" style={{ background: 'transparent', border: '1px solid #292524', color: '#a8a29e', fontSize: 13, fontWeight: 500, padding: '8px 18px', borderRadius: 8, textDecoration: 'none' }}>
            {t('legal.signIn')}
          </Link>
          <Link to="/sign-up" style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 20px', borderRadius: 8, textDecoration: 'none' }}>
            {t('legal.getStarted')}
          </Link>
        </div>
      </nav>

      {/* CONTENT */}
      <main style={{ maxWidth: 760, margin: '0 auto', padding: '64px 32px 80px' }}>
        <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#22c55e', marginBottom: 12 }}>
          {t('legal.label')}
        </div>
        <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 44, fontWeight: 700, letterSpacing: '-0.03em', marginBottom: 12 }}>
          {title}
        </h1>
        <div style={{ fontSize: 13, color: '#a8a29e', marginBottom: 40 }}>
          {t('legal.lastUpdatedLabel')}: {lastUpdated}
        </div>

        {disclaimer && (
          <div
            style={{
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 12,
              padding: 20,
              marginBottom: 32,
              color: '#fafaf9',
              fontSize: 14,
              lineHeight: 1.7,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#ef4444', marginBottom: 8 }}>
              {t('legal.disclaimerLabel')}
            </div>
            {disclaimer}
          </div>
        )}

        {intro && (
          <p style={{ fontSize: 15, color: '#d6d3d1', lineHeight: 1.75, marginBottom: 32 }}>
            {intro}
          </p>
        )}

        {sections.map((s, i) => (
          <section key={i} style={{ marginBottom: 32 }}>
            <h2 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 12, color: '#fafaf9' }}>
              {i + 1}. {s.title}
            </h2>
            {s.body.split('\n\n').map((para, j) => (
              <p key={j} style={{ fontSize: 14.5, color: '#a8a29e', lineHeight: 1.75, marginBottom: 12 }}>
                {linkifyEmails(para)}
              </p>
            ))}
          </section>
        ))}

        <div style={{ marginTop: 48, padding: 20, background: '#1c1917', border: '1px solid #292524', borderRadius: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#d6d3d1', marginBottom: 6 }}>{t('legal.contactTitle')}</div>
          <div style={{ fontSize: 14 }}>
            <EmailLink email={contactEmail} />
          </div>
          <div style={{ fontSize: 12, color: '#a8a29e', marginTop: 4 }}>{t('legal.clickToCopy')}</div>
        </div>

        {children}
      </main>

      {/* FOOTER */}
      <footer style={{ borderTop: '1px solid #292524', padding: '32px 64px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
        <span style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: 16, fontWeight: 700, color: '#d6d3d1' }}>StockPro</span>
        <div style={{ display: 'flex', gap: 24 }}>
          <Link to="/legal/privacy" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>{t('legal.footerLinks.privacy')}</Link>
          <Link to="/legal/terms" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>{t('legal.footerLinks.terms')}</Link>
          <Link to="/legal/refund" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>{t('legal.footerLinks.refund')}</Link>
          <a href="mailto:ojs.stockpro@gmail.com" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>{t('legal.footerLinks.contact')}</a>
        </div>
        <span style={{ fontSize: 12, color: '#a8a29e' }}>&copy; 2026 StockPro</span>
      </footer>
    </div>
  )
}
