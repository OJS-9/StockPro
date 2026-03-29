# Phase 1 — User-facing change notes (templates)

Use these short blurbs in-product, email footers, or changelog entries. Replace bracketed placeholders when engineering confirms final behavior.

---

## Environment / setup (if users self-host or use developer preview)

**Title:** Clearer setup for local and staging environments  

**Body:** We updated environment documentation and dependency pinning so installs match what we run in CI. If you had a custom `.env`, compare it to the latest `.env.example`—no action needed unless your build stopped working.

---

## Supabase / authentication

**Title:** Account security and sign-in  

**Body:** We’re verifying our Supabase configuration (sessions, redirects, and email flows) as part of Phase 1 reliability. If you notice unexpected sign-out behavior or email link issues, contact support with your browser and approximate time—we’re monitoring closely during this window.

*Ship-only variant (if no user-visible auth UI change):* Internal hardening only; no change to how you sign in.

---

## Mobile layout

**Title:** Better experience on phones and tablets  

**Body:** We prioritized responsive layouts on core screens so research and navigation stay usable on small viewports. If something still breaks on your device, tell us the device model and browser version.

---

## CI / reliability (internal-only; keep for post-launch recap)

**Title:** Faster, safer releases  

**Body:** Behind the scenes we expanded automated tests and deployment checks so fixes ship with fewer regressions. No action required.

---

## Voice

- Calm, specific, no hype.  
- Pair any “we improved” claim with *what the user might notice* or *when to contact us*.
