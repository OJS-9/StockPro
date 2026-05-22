import { StrictMode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ClerkProvider } from '@clerk/clerk-react'
import { Toaster } from 'react-hot-toast'
import App from './App.tsx'
import { LanguageProvider, useLanguage } from './LanguageContext'
import { ResearchProgressProvider } from './ResearchProgressContext'
import './i18n'
import './index.css'

const CLERK_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
if (!CLERK_KEY) throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY')

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 120_000 } },
})

function AppToaster() {
  const { dir } = useLanguage()
  return (
    <Toaster
      position={dir === 'rtl' ? 'bottom-left' : 'bottom-right'}
      toastOptions={{
        style: { background: '#1c1917', color: '#fff', border: '1px solid #292524' },
      }}
    />
  )
}

const rootEl = document.getElementById('root')!

const tree = (
  <StrictMode>
    <ClerkProvider publishableKey={CLERK_KEY}>
      <QueryClientProvider client={queryClient}>
        <LanguageProvider>
          <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || '/'}>
            <ResearchProgressProvider>
              <App />
              <AppToaster />
            </ResearchProgressProvider>
          </BrowserRouter>
        </LanguageProvider>
      </QueryClientProvider>
    </ClerkProvider>
  </StrictMode>
)

// If vite-prerender-plugin baked Landing HTML into the root at build time,
// hydrate over it. Otherwise (dev, or routes without prerender), do a fresh mount.
if (rootEl.hasChildNodes()) {
  hydrateRoot(rootEl, tree)
} else {
  createRoot(rootEl).render(tree)
}
