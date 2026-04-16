import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ClerkProvider } from '@clerk/clerk-react'
import { Toaster } from 'react-hot-toast'
import App from './App.tsx'
import { LanguageProvider, useLanguage } from './LanguageContext'
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={CLERK_KEY}>
      <QueryClientProvider client={queryClient}>
        <LanguageProvider>
          <BrowserRouter basename="/app">
            <App />
            <AppToaster />
          </BrowserRouter>
        </LanguageProvider>
      </QueryClientProvider>
    </ClerkProvider>
  </StrictMode>,
)
