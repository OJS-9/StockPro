// Build-time prerender entrypoint. vite-prerender-plugin invokes prerender()
// during `vite build` and bakes the returned HTML into dist/index.html, so
// non-JS crawlers (GPTBot, PerplexityBot, ClaudeBot, etc.) receive the full
// Landing page markup instead of an empty <div id="root">.
//
// Notes:
// - We deliberately skip ClerkProvider here. Clerk requires a publishable key
//   and touches browser APIs; the prerendered HTML is for the unauthenticated
//   first paint anyway, so we just render Landing inside a MemoryRouter.
// - Hydration matches because the client's `/` route renders Landing during
//   Clerk's loading state too (see App.tsx).
import { renderToString } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import Landing from './pages/Landing'

export async function prerender() {
  const html = renderToString(
    <MemoryRouter initialEntries={['/']}>
      <Landing />
    </MemoryRouter>
  )
  return { html }
}
