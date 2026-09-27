import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useLeaderboard } from '../lib/queries'
import { useSession } from '../lib/session'
import { Avatar, Icon, Logo, StreakPill, Wordmark } from './ui'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/submit', label: 'Submit Task' },
  { to: '/leaderboard', label: 'Leaderboard' },
  { to: '/grading', label: 'AI Grading' },
  { to: '/jobs', label: 'Job Tracker' },
]

function useClickOutside(onOutside: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const handler = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onOutside()
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onOutside])
  return ref
}

function ChallengeSwitcher() {
  const { challenges, challenge, selectChallenge } = useSession()
  const [open, setOpen] = useState(false)
  const ref = useClickOutside(() => setOpen(false))
  const navigate = useNavigate()
  if (!challenge) return null
  return (
    <div ref={ref} className="relative hidden lg:block">
      <button
        className="flex items-center gap-2 rounded-full bg-surface-container-low px-3 py-1 transition-colors hover:bg-surface-container-high"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="h-2 w-2 shrink-0 rounded-full bg-secondary" />
        <span className="max-w-[200px] truncate font-mono text-label-sm text-on-surface">{challenge.name}</span>
        <Icon name="expand_more" className="text-[18px] text-on-surface-variant" />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-2 w-72 rounded-xl bg-white p-1 shadow-modal">
          {challenges.map((c) => (
            <button
              key={c.id}
              className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left hover:bg-surface-container-low ${c.id === challenge.id ? 'text-primary-container' : 'text-ink'}`}
              onClick={() => {
                selectChallenge(c.id)
                setOpen(false)
              }}
            >
              <span className="truncate">{c.name}</span>
              {c.id === challenge.id && <Icon name="check" className="text-[18px]" />}
            </button>
          ))}
          <div className="my-1 h-px bg-slate-100" />
          <button
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-on-surface-variant hover:bg-surface-container-low"
            onClick={() => {
              setOpen(false)
              navigate('/join')
            }}
          >
            <Icon name="add" className="text-[18px]" /> Join another challenge
          </button>
        </div>
      )}
    </div>
  )
}

function UserMenu() {
  const { user, signOut } = useSession()
  const [open, setOpen] = useState(false)
  const ref = useClickOutside(() => setOpen(false))
  if (!user) return null
  return (
    <div ref={ref} className="relative">
      <button className="flex items-center gap-2 rounded-full py-1 pr-2 pl-1 hover:bg-surface-container-low" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Avatar name={user.name} id={user.id} size={32} />
        <span className="hidden text-body-md font-medium text-ink md:inline">{user.name}</span>
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-2 w-56 rounded-xl bg-white p-1 shadow-modal" onClick={() => setOpen(false)}>
          <div className="px-3 py-2">
            <p className="truncate font-medium text-ink">{user.name}</p>
            <p className="truncate text-body-sm text-on-surface-variant">{user.email}</p>
          </div>
          <div className="my-1 h-px bg-slate-100" />
          <Link to="/settings" className="flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-surface-container-low">
            <Icon name="settings" className="text-[18px]" /> Settings
          </Link>
          {user.is_admin && (
            <Link to="/admin" className="flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-surface-container-low">
              <Icon name="admin_panel_settings" className="text-[18px]" /> Admin
            </Link>
          )}
          <button onClick={signOut} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-error hover:bg-error-container/40">
            <Icon name="logout" className="text-[18px]" /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}

export function AppShell() {
  const { user, challenge } = useSession()
  const board = useLeaderboard(challenge?.id)
  const myRow = board.data?.find((r) => r.user_id === user?.id)
  // The mobile menu is open for the page it was opened on; navigating closes it.
  const { pathname } = useLocation()
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const menuOpen = menuFor === pathname

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-1.5 transition-colors ${isActive ? 'bg-primary-container text-white font-medium' : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'}`

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-50 bg-surface/90 shadow-[0_1px_8px_rgba(0,0,0,0.04)] backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-4 px-4 md:px-margin">
          <div className="flex shrink-0 items-center gap-4">
            <button className="btn-ghost h-9 px-2 xl:hidden" onClick={() => setMenuFor(menuOpen ? null : pathname)} aria-label="Menu">
              <Icon name={menuOpen ? 'close' : 'menu'} />
            </button>
            <Link to="/" className="flex items-center gap-2">
              <Logo size={30} />
              <Wordmark className="hidden text-headline-md sm:inline" />
            </Link>
            <div className="hidden h-5 w-px bg-surface-container-high lg:block" />
            <ChallengeSwitcher />
          </div>
          <nav className="hidden items-center gap-1 xl:flex">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={linkClass}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            {myRow && <StreakPill days={myRow.current_streak} className="hidden sm:inline-flex" />}
            <UserMenu />
          </div>
        </div>
        {menuOpen && (
          <nav className="flex flex-col gap-1 border-t border-slate-100 px-4 py-3 xl:hidden">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={linkClass}>
                {n.label}
              </NavLink>
            ))}
            <NavLink to="/join" className={linkClass}>
              Switch / join challenge
            </NavLink>
          </nav>
        )}
      </header>

      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 md:px-margin md:py-8">
        <Outlet />
      </main>

      <footer className="bg-surface-container-low">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-2 px-4 py-6 text-body-sm text-on-surface-variant sm:flex-row sm:items-center sm:justify-between md:px-margin">
          <span>
            <Wordmark className="text-ink" /> · Stay accountable, build consistency.
          </span>
          <span className="font-mono text-label-sm">{user?.email}</span>
        </div>
      </footer>
    </div>
  )
}
