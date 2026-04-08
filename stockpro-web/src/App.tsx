import { useRef, useEffect, lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router'
import { SignedIn, SignedOut } from '@clerk/clerk-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { useApiClient } from './api/client'

// Eager: small pages needed immediately
import Landing from './pages/Landing'
import SignIn from './pages/SignIn'
import SignUp from './pages/SignUp'

// Lazy: all authenticated pages
const Home = lazy(() => import('./pages/Home'))
const PortfolioList = lazy(() => import('./pages/PortfolioList'))
const PortfolioDetail = lazy(() => import('./pages/PortfolioDetail'))
const AddTransaction = lazy(() => import('./pages/AddTransaction'))
const ImportCSV = lazy(() => import('./pages/ImportCSV'))
const HoldingDetail = lazy(() => import('./pages/HoldingDetail'))
const Analytics = lazy(() => import('./pages/Analytics'))
const ReportsHistory = lazy(() => import('./pages/ReportsHistory'))
const ReportView = lazy(() => import('./pages/ReportView'))
const Chat = lazy(() => import('./pages/Chat'))
const ResearchWizard = lazy(() => import('./pages/ResearchWizard'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const Alerts = lazy(() => import('./pages/Alerts'))
const TickerPage = lazy(() => import('./pages/TickerPage'))
const Settings = lazy(() => import('./pages/Settings'))

/**
 * Runs at app level (never unmounts on navigation) so toast dedup works.
 * Only toasts notifications arriving AFTER mount to avoid flooding on login.
 */
function NotificationListener() {
  const api = useApiClient()
  const shownIds = useRef<Set<string>>(new Set())
  const baselineTs = useRef<string | null>(null)
  const initialized = useRef(false)

  const { data } = useQuery({
    queryKey: ['alert-notifications'],
    queryFn: async () => {
      const res = await api.get('/api/alerts/notifications?limit=20')
      if (!res.ok) return { notifications: [], unread_count: 0 }
      return res.json()
    },
    refetchInterval: 30_000,
    staleTime: 25_000,
  })

  const notifications: any[] = data?.notifications ?? []

  if (notifications.length > 0 && !initialized.current) {
    baselineTs.current = notifications[0]?.created_at ?? null
    initialized.current = true
  } else if (initialized.current) {
    const newUnread = notifications.filter(
      (n: any) =>
        !n.read_at &&
        !shownIds.current.has(n.notification_id) &&
        baselineTs.current &&
        n.created_at > baselineTs.current
    )
    if (newUnread.length > 0) {
      newUnread.forEach((n: any) => {
        shownIds.current.add(n.notification_id)
        toast(n.body, {
          duration: 6000,
          style: {
            background: '#1c1917',
            color: '#fafaf9',
            border: '1px solid #292524',
            fontSize: 13,
          },
        })
      })
    }
  }

  return null
}

/** Prefetch all page data once on login so navigation is instant. */
function DataPrefetcher() {
  const api = useApiClient()
  const queryClient = useQueryClient()

  useEffect(() => {
    const pages = [
      { key: ['home'], url: '/api/home' },
      { key: ['portfolios'], url: '/api/portfolios/prices' },
      { key: ['watchlists'], url: '/api/watchlists' },
      { key: ['reports'], url: '/api/reports' },
      { key: ['alerts'], url: '/api/alerts' },
    ]
    pages.forEach(({ key, url }) => {
      queryClient.prefetchQuery({
        queryKey: key,
        queryFn: async () => {
          const res = await api.get(url)
          if (!res.ok) throw new Error('Failed')
          return res.json()
        },
        staleTime: 120_000,
      })
    })
  }, [])

  return null
}

export default function App() {
  return (
    <>
    <SignedIn><NotificationListener /><DataPrefetcher /></SignedIn>
    <Suspense fallback={<div style={{ background: '#0c0a09', minHeight: '100vh' }} />}>
    <Routes>
      {/* Root: landing for unauthenticated, redirect to /home for signed in */}
      <Route
        path="/"
        element={
          <>
            <SignedIn>
              <Navigate to="/home" replace />
            </SignedIn>
            <SignedOut>
              <Landing />
            </SignedOut>
          </>
        }
      />

      {/* Auth pages */}
      <Route path="/sign-in/*" element={<SignIn />} />
      <Route path="/sign-up/*" element={<SignUp />} />

      {/* Authenticated app pages */}
      <Route
        path="/home"
        element={
          <SignedIn>
            <Home />
          </SignedIn>
        }
      />

      <Route
        path="/portfolio"
        element={
          <SignedIn>
            <PortfolioList />
          </SignedIn>
        }
      />

      <Route
        path="/portfolio/:id"
        element={
          <SignedIn>
            <PortfolioDetail />
          </SignedIn>
        }
      />

      <Route
        path="/portfolio/:id/add"
        element={
          <SignedIn>
            <AddTransaction />
          </SignedIn>
        }
      />

      <Route
        path="/portfolio/:id/import"
        element={
          <SignedIn>
            <ImportCSV />
          </SignedIn>
        }
      />

      <Route
        path="/portfolio/:id/holding/:symbol"
        element={
          <SignedIn>
            <HoldingDetail />
          </SignedIn>
        }
      />

      <Route
        path="/portfolio/:id/analytics"
        element={
          <SignedIn>
            <Analytics />
          </SignedIn>
        }
      />

      <Route
        path="/reports"
        element={
          <SignedIn>
            <ReportsHistory />
          </SignedIn>
        }
      />

      <Route
        path="/report/:id"
        element={
          <SignedIn>
            <ReportView />
          </SignedIn>
        }
      />

      <Route
        path="/chat/:reportId"
        element={
          <SignedIn>
            <Chat />
          </SignedIn>
        }
      />

      <Route
        path="/research"
        element={
          <SignedIn>
            <ResearchWizard />
          </SignedIn>
        }
      />

      <Route
        path="/watchlist"
        element={
          <SignedIn>
            <Watchlist />
          </SignedIn>
        }
      />

      <Route
        path="/alerts"
        element={
          <SignedIn>
            <Alerts />
          </SignedIn>
        }
      />

      <Route
        path="/ticker/:symbol"
        element={
          <SignedIn>
            <TickerPage />
          </SignedIn>
        }
      />

      <Route
        path="/settings"
        element={
          <SignedIn>
            <Settings />
          </SignedIn>
        }
      />

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
    </>
  )
}
