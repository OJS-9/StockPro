# StockPro — Phase 1 waitlist & landing copy (Weeks 1–3 aligned)

**Status:** Draft for review with [Lead Engineer](/STOA/agents/lead-engineer) before any public URL goes live.  
**Scope alignment:** Phase 1 ships foundation work (Supabase verification, mobile responsiveness, CI/CD, tests, security, pipeline reliability) per [STOA-4](/STOA/issues/STOA-4#document-plan) / [STOA-6](/STOA/issues/STOA-6). Copy avoids promising Phase 2+ capabilities (observability dashboards, real-time streaming, brokerage, PWA) until those ship.

---

## Hero

**Headline:** Institutional-grade stock research in minutes, not hours.

**Subhead:** StockPro uses a 12-subject AI agent pipeline to produce equity research reports you can act on—fast.

**Primary CTA:** Join the waitlist  
**Secondary CTA:** How it works (anchor to `#how-it-works`)

---

## Value props (three columns or bullets)

1. **Depth without the desk** — Multi-agent analysis across fundamentals, sentiment, risk, and context—structured like research you’d expect from a serious process, delivered in minutes.
2. **Built for real portfolios** — Clear outputs aimed at decisions, not generic summaries.
3. **Early access** — We’re rolling out carefully while we harden the stack (mobile, reliability, and data integrity first).

---

## How it works (`#how-it-works`)

1. **Tell us what you’re researching** — Ticker, horizon, and what you need to validate.
2. **Agents run in parallel** — Twelve focused passes synthesize into one report.
3. **Review and iterate** — Export or refine; we’re optimizing for repeatability and trust.

---

## Trust & expectations (fine print block)

StockPro provides research-style outputs for information purposes only, not personalized investment advice. Markets involve risk; past patterns do not guarantee future results. Early access may mean occasional maintenance windows while we improve performance and security.

---

## Waitlist form microcopy

- **Email label:** Work email (recommended)  
- **Helper text:** We’ll send product updates and one invite when your batch opens. No spam.  
- **Consent (if required):** Checkbox label: *I agree to receive StockPro waitlist and product emails.*

---

## Engineering coordination notes

- If Weeks 1–3 introduce **auth changes** (e.g., Supabase email/OAuth), pair this page with `phase1-user-facing-change-notes.md` for user comms.
- Before publishing: confirm hero/CTA match whatever landing route actually ships (static page vs app shell).
