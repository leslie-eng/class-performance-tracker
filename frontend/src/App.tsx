import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { PageLoader } from './components/ui'
import { useSession } from './lib/session'
import AdminPage from './pages/Admin'
import DashboardPage from './pages/Dashboard'
import GradingPage from './pages/Grading'
import JobsPage from './pages/Jobs'
import JoinPage from './pages/Join'
import LeaderboardPage from './pages/Leaderboard'
import LoginPage from './pages/Login'
import SettingsPage from './pages/Settings'
import SubmitPage from './pages/Submit'

function RequireAuth({ children }: { children: ReactNode }) {
  const { token, user, userLoading } = useSession()
  const location = useLocation()
  if (!token) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (userLoading || !user) return <PageLoader />
  return children
}

/** Pages that only make sense once the member has joined a challenge. */
function RequireChallenge({ children }: { children: ReactNode }) {
  const { challenge, challengesLoading } = useSession()
  if (challengesLoading) return <PageLoader />
  if (!challenge) return <Navigate to="/join" replace />
  return children
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useSession()
  return user?.is_admin ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<RequireChallenge><DashboardPage /></RequireChallenge>} />
        <Route path="/submit" element={<RequireChallenge><SubmitPage /></RequireChallenge>} />
        <Route path="/leaderboard" element={<RequireChallenge><LeaderboardPage /></RequireChallenge>} />
        <Route path="/grading" element={<GradingPage />} />
        <Route path="/grading/:id" element={<GradingPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/join" element={<JoinPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/admin" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
