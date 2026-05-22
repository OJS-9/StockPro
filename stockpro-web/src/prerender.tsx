// Build-time prerender entrypoint. vite-prerender-plugin invokes prerender()
// during `vite build` and bakes the returned HTML into dist/<route>.html, so
// non-JS crawlers (GPTBot, PerplexityBot, ClaudeBot, etc.) receive the full
// markup instead of an empty <div id="root">.
//
// We render `/` (Landing), `/about`, and `/press`. Authority-signal pages
// benefit most from prerendering since AI engines weight E-E-A-T heavily.
//
// Notes:
// - We deliberately skip ClerkProvider here. Clerk requires a publishable key
//   and touches browser APIs; the prerendered HTML is for the unauthenticated
//   first paint anyway.
// - Hydration matches because the client routes render the same component
//   without auth gating.
import { renderToString } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import Landing from './pages/Landing'
import About from './pages/About'
import Press from './pages/Press'

export async function prerender(data: { url: string }) {
  const url = data?.url || '/'

  let Component: () => any = Landing
  if (url === '/about') Component = About
  else if (url === '/press') Component = Press

  const html = renderToString(
    <MemoryRouter initialEntries={[url]}>
      <Component />
    </MemoryRouter>
  )
  return { html }
}
