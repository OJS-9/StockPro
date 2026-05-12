import { Link } from 'react-router'
import { useState, useEffect } from 'react'

const PRESS_EMAIL = 'optimusor@gmail.com'

const BOILERPLATE = `StockPro (stock-pro.org) is an AI-powered stock and crypto research platform built by solo founder Or Joshua Salinas. It runs 12 specialized AI research agents in parallel — covering fundamentals, technicals, risk, competitive landscape, and news sentiment — to produce institutional-quality research reports on any ticker in under three minutes. The product also includes portfolio tracking, watchlists, and real-time price alerts. StockPro is free to use, with paid tiers for higher report volume. The platform is built on a modern multi-agent AI stack and is independently operated.`

export default function Press() {
  const [isMobile, setIsMobile] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const update = () => setIsMobile(window.innerWidth < 768)
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  const copyBoilerplate = () => {
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(BOILERPLATE).then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      })
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0c0a09', color: '#fafaf9', fontFamily: 'Inter, Heebo, sans-serif' }}>
      {/* NAV */}
      <nav
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: isMobile ? '0 20px' : '0 64px', height: 64,
          position: 'sticky', top: 0, zIndex: 100,
          background: 'rgba(12,10,9,0.9)', backdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(41,37,36,0.6)',
        }}
      >
        <Link to="/" style={{ textDecoration: 'none' }}>
          <span style={{ fontFamily: 'Nunito, sans-serif', fontSize: 18, fontWeight: 700, color: '#d6d3d1', letterSpacing: '-0.02em' }}>StockPro</span>
        </Link>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link to="/sign-up" style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 20px', borderRadius: 8, textDecoration: 'none' }}>
            Get started
          </Link>
        </div>
      </nav>

      <main style={{ maxWidth: 760, margin: '0 auto', padding: isMobile ? '40px 20px 60px' : '64px 32px 80px' }}>
        <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#22c55e', marginBottom: 12 }}>
          Press kit
        </div>
        <h1 style={{ fontFamily: 'Nunito, sans-serif', fontSize: isMobile ? 36 : 48, fontWeight: 700, letterSpacing: '-0.03em', marginBottom: 16, lineHeight: 1.1 }}>
          Press &amp; media
        </h1>
        <p style={{ fontSize: 17, color: '#d6d3d1', lineHeight: 1.6, marginBottom: 40 }}>
          Institutional-grade stock research, built solo and free for retail investors.
        </p>

        {/* Quick facts */}
        <section style={{ marginBottom: 40 }}>
          <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, marginBottom: 16 }}>Quick facts</h2>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12 }}>
            {[
              { label: 'Founder', value: 'Or Joshua Salinas' },
              { label: 'Launched', value: '2026' },
              { label: 'HQ', value: 'Remote / Independent' },
              { label: 'Website', value: 'stock-pro.org' },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 12, padding: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#22c55e', marginBottom: 6 }}>{label}</div>
                <div style={{ fontSize: 14, color: '#d6d3d1' }}>{value}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Boilerplate */}
        <section style={{ marginBottom: 40 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, margin: 0 }}>Boilerplate</h2>
            <button onClick={copyBoilerplate}
              style={{ background: 'transparent', border: '1px solid #292524', color: '#d6d3d1', fontSize: 12, fontWeight: 600, padding: '6px 14px', borderRadius: 8, cursor: 'pointer' }}>
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 12, padding: 20, fontSize: 14, color: '#a8a29e', lineHeight: 1.7 }}>
            {BOILERPLATE}
          </div>
        </section>

        {/* Brand assets */}
        <section style={{ marginBottom: 40 }}>
          <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, marginBottom: 16 }}>Brand assets</h2>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <a href="/app/favicon.svg" target="_blank" rel="noopener"
              style={{ background: '#1c1917', border: '1px solid #292524', color: '#d6d3d1', fontSize: 13, fontWeight: 500, padding: '12px 18px', borderRadius: 10, textDecoration: 'none' }}>
              Download logo (SVG)
            </a>
            <a href="/app/og-image.png" target="_blank" rel="noopener"
              style={{ background: '#1c1917', border: '1px solid #292524', color: '#d6d3d1', fontSize: 13, fontWeight: 500, padding: '12px 18px', borderRadius: 10, textDecoration: 'none' }}>
              Social card (PNG)
            </a>
          </div>
        </section>

        {/* As seen in */}
        <section style={{ marginBottom: 40 }}>
          <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, marginBottom: 16 }}>As seen in</h2>
          <div style={{ background: '#1c1917', border: '1px dashed #292524', borderRadius: 12, padding: 24, textAlign: 'center', color: '#78716c', fontSize: 13 }}>
            Press mentions will appear here.
          </div>
        </section>

        {/* Contact */}
        <section>
          <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, marginBottom: 16 }}>Press contact</h2>
          <div style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 12, padding: 20 }}>
            <div style={{ fontSize: 13, color: '#a8a29e', marginBottom: 8 }}>Or Joshua Salinas, founder</div>
            <a href={`mailto:${PRESS_EMAIL}`} style={{ color: '#22c55e', fontSize: 16, textDecoration: 'underline' }}>
              {PRESS_EMAIL}
            </a>
          </div>
        </section>
      </main>

      {/* FOOTER */}
      <footer style={{ borderTop: '1px solid #292524', padding: isMobile ? '24px 20px' : '32px 64px', display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: 16, alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: 'Nunito, sans-serif', fontSize: 16, fontWeight: 700, color: '#d6d3d1' }}>StockPro</span>
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', justifyContent: 'center' }}>
          <Link to="/about" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>About</Link>
          <Link to="/press" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>Press</Link>
          <Link to="/legal/privacy" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>Privacy</Link>
          <Link to="/legal/terms" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>Terms</Link>
        </div>
        <span style={{ fontSize: 12, color: '#a8a29e' }}>&copy; 2026 StockPro</span>
      </footer>
    </div>
  )
}
