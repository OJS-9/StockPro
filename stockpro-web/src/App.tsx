import { useRef } from 'react'
import { Routes, Route, Navigate } from 'react-router'
import { SignedIn, SignedOut } from '@clerk/clerk-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { useApiClient } from './api/client'

import Landing from './pages/Landing'
import Home from './pages/Home'
import SignIn from './pages/SignIn'
import SignUp from './pages/SignUp'
import PortfolioList from './pages/PortfolioList'
import PortfolioDetail from './pages/PortfolioDetail'
import AddTransaction from './pages/AddTransaction'
import ImportCSV from './pages/ImportCSV'
import HoldingDetail from './pages/HoldingDetail'
import Analytics from './pages/Analytics'
import ReportsHistory from './pages/ReportsHistory'
import ReportView from './pages/ReportView'
import Chat from './pages/Chat'
import ResearchWizard from './pages/ResearchWizard'
import Watchlist from './pages/Watchlist'
import Alerts from './pages/Alerts'
import TickerPage from './pages/TickerPage'
import Settings from './pages/Settings'

/**
 * Runs at app level (never unmounts on navigation) so toast dedup works.
 * Only toasts notifications arriving AFTER mount to avoid flooding on login.
 */
function NotificationListener() {
  const api = useApiClient()
  const queryClient = useQueryClient()
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
        api.patch(`/api/alerts/notifications/${n.notification_id}`, { read: true }).then(() => {
          queryClient.invalidateQueries({ queryKey: ['alert-notifications'] })
        })
      })
    }
  }

  return null
}

export default function App() {
  return (
    <>
    <SignedIn><NotificationListener /></SignedIn>
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
    </>
  )
}
