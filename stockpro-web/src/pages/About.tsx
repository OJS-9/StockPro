import { Link } from 'react-router'
import { useState, useEffect } from 'react'

const FOUNDER_IMG = '/app/founder.jpg'
const INITIALS = 'OS'

export default function About() {
  const [imgOk, setImgOk] = useState(true)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const update = () => setIsMobile(window.innerWidth < 768)
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: '#0c0a09', color: '#fafaf9', fontFamily: 'Inter, Heebo, sans-serif' }}>
      {/* NAV */}
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: isMobile ? '0 20px' : '0 64px',
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
            Sign in
          </Link>
          <Link to="/sign-up" style={{ background: '#d6d3d1', color: '#0c0a09', fontSize: 13, fontWeight: 600, padding: '8px 20px', borderRadius: 8, textDecoration: 'none' }}>
            Get started
          </Link>
        </div>
      </nav>

      {/* HERO */}
      <main style={{ maxWidth: 760, margin: '0 auto', padding: isMobile ? '40px 20px 60px' : '64px 32px 80px' }}>
        <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#22c55e', marginBottom: 12 }}>
          About
        </div>
        <h1 style={{ fontFamily: 'Nunito, "Secular One", Heebo, sans-serif', fontSize: isMobile ? 36 : 48, fontWeight: 700, letterSpacing: '-0.03em', marginBottom: 24, lineHeight: 1.1 }}>
          Built solo, in the open.
        </h1>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 40, padding: 20, background: '#1c1917', border: '1px solid #292524', borderRadius: 14 }}>
          {imgOk ? (
            <img
              src={FOUNDER_IMG}
              alt="Or Joshua Salinas"
              onError={() => setImgOk(false)}
              style={{ width: 80, height: 80, borderRadius: '50%', objectFit: 'cover', border: '2px solid #292524' }}
            />
          ) : (
            <div
              aria-label="Or Joshua Salinas"
              style={{
                width: 80, height: 80, borderRadius: '50%',
                background: 'linear-gradient(135deg, #292524 0%, #44403c 100%)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: 'Nunito, sans-serif', fontSize: 28, fontWeight: 700, color: '#d6d3d1',
                border: '2px solid #292524',
              }}
            >
              {INITIALS}
            </div>
          )}
          <div>
            <div style={{ fontFamily: 'Nunito, sans-serif', fontSize: 20, fontWeight: 700, color: '#fafaf9' }}>Or Joshua Salinas</div>
            <div style={{ fontSize: 14, color: '#a8a29e', marginTop: 4 }}>Founder &amp; sole engineer, StockPro</div>
          </div>
        </div>

        {/* BIO */}
        <section style={{ marginBottom: 48 }}>
          <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 16 }}>
            Hi, I'm Or.
          </h2>
          <p style={{ fontSize: 16, color: '#d6d3d1', lineHeight: 1.75, marginBottom: 16 }}>
            StockPro started as a tool I needed for myself.
          </p>
          <p style={{ fontSize: 15, color: '#a8a29e', lineHeight: 1.75, marginBottom: 16 }}>
            I'm Or Joshua Salinas — a self-taught builder. My background is a mix: I've spent serious time thinking about
            markets and investing, taught myself to code and ship real software, and watched the AI landscape evolve to
            the point where — sometime in late 2025 — products like this finally became possible for one person to build
            end-to-end.
          </p>
        </section>

        {/* WHY */}
        <section style={{ marginBottom: 48 }}>
          <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 16 }}>
            Why I built StockPro
          </h2>
          <p style={{ fontSize: 15, color: '#a8a29e', lineHeight: 1.75, marginBottom: 16 }}>
            The pitch is simple. Institutional-quality stock research is locked behind Bloomberg terminals,
            $30k-a-year analyst services, and walled gardens. Retail investors get screeners that filter tickers but
            don't explain them. With modern multi-agent LLMs, one solo builder can deliver the same depth of research a
            junior analyst at a fund would produce — in three minutes, for free.
          </p>
          <p style={{ fontSize: 15, color: '#a8a29e', lineHeight: 1.75 }}>
            That's StockPro: 12 specialized AI agents that research a ticker in parallel and synthesize what they find
            into a real report. Not a chatbot. Not a screener. Actual research, grounded in real market data.
          </p>
        </section>

        {/* HOW IT WORKS */}
        <section style={{ marginBottom: 48 }}>
          <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 16 }}>
            How it works
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12 }}>
            {[
              { label: 'The team', value: 'A team of 12 specialist AI agents — fundamentals, technicals, risk, competitive landscape, news sentiment, and more — working in parallel on every ticker.' },
              { label: 'Grounded in real data', value: 'Every report pulls from live market data, financial filings, and real-time web sources. No vibes. No hallucinated numbers.' },
              { label: 'Three minutes, end to end', value: 'A planner picks the right specialists, they research in parallel, a quality gate filters weak output, and a synthesis agent merges it into one report.' },
              { label: 'Framed around you', value: "When you've connected a portfolio, the research is framed against your actual positions — not a generic write-up." },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: '#1c1917', border: '1px solid #292524', borderRadius: 12, padding: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#22c55e', marginBottom: 6 }}>{label}</div>
                <div style={{ fontSize: 13, color: '#d6d3d1', lineHeight: 1.5 }}>{value}</div>
              </div>
            ))}
          </div>
        </section>

        {/* SOCIAL */}
        <section style={{ marginBottom: 32 }}>
          <h2 style={{ fontFamily: 'Nunito, sans-serif', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 16 }}>
            Get in touch
          </h2>
          <p style={{ fontSize: 15, color: '#a8a29e', lineHeight: 1.75, marginBottom: 20 }}>
            Built solo, in the open. If you have feedback or want to chat, find me here:
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            <a href="https://x.com/OJSsalinas" target="_blank" rel="noopener noreferrer me"
              style={{ background: '#1c1917', border: '1px solid #292524', color: '#d6d3d1', fontSize: 14, fontWeight: 500, padding: '10px 18px', borderRadius: 10, textDecoration: 'none' }}>
              X / Twitter
            </a>
            <a href="https://www.linkedin.com/in/or-joshua-s-891a22141/" target="_blank" rel="noopener noreferrer me"
              style={{ background: '#1c1917', border: '1px solid #292524', color: '#d6d3d1', fontSize: 14, fontWeight: 500, padding: '10px 18px', borderRadius: 10, textDecoration: 'none' }}>
              LinkedIn
            </a>
            <a href="https://github.com/OJS-9" target="_blank" rel="noopener noreferrer me"
              style={{ background: '#1c1917', border: '1px solid #292524', color: '#d6d3d1', fontSize: 14, fontWeight: 500, padding: '10px 18px', borderRadius: 10, textDecoration: 'none' }}>
              GitHub
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
          <Link to="/legal/refund" style={{ fontSize: 13, color: '#a8a29e', textDecoration: 'none' }}>Refund</Link>
        </div>
        <span style={{ fontSize: 12, color: '#a8a29e' }}>&copy; 2026 StockPro</span>
      </footer>
    </div>
  )
}
