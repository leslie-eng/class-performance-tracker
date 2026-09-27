import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getToken, setToken, setUnauthorizedHandler } from './api'
import { useMe, useMeta, useMyChallenges } from './queries'
import type { Challenge, Meta, User } from './types'

const CHALLENGE_KEY = 'classtrack.challenge'

interface Session {
  token: string | null
  user: User | undefined
  userLoading: boolean
  meta: Meta | undefined
  challenges: Challenge[]
  challengesLoading: boolean
  challenge: Challenge | undefined
  selectChallenge: (id: number) => void
  signIn: (token: string, remember: boolean) => void
  signOut: () => void
}

const SessionContext = createContext<Session | null>(null)

function readSelected(): number | null {
  try {
    return Number(localStorage.getItem(CHALLENGE_KEY)) || null
  } catch {
    return null
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [token, setTokenState] = useState(getToken)
  const [selected, setSelected] = useState<number | null>(readSelected)

  const me = useMe(!!token)
  const meta = useMeta()
  const mine = useMyChallenges(!!token)

  const signOut = useCallback(() => {
    setToken(null)
    setTokenState(null)
    qc.clear()
  }, [qc])

  useEffect(() => setUnauthorizedHandler(signOut), [signOut])

  const signIn = useCallback(
    (t: string, remember: boolean) => {
      setToken(t, remember)
      setTokenState(t)
      qc.invalidateQueries()
    },
    [qc],
  )

  const selectChallenge = useCallback((id: number) => {
    setSelected(id)
    try {
      localStorage.setItem(CHALLENGE_KEY, String(id))
    } catch {
      /* ignore */
    }
  }, [])

  const challenges = useMemo(() => (token ? (mine.data ?? []) : []), [token, mine.data])
  const challenge = useMemo(() => {
    const picked = challenges.find((c) => c.id === selected)
    if (picked) return picked
    const today = meta.data?.today
    return challenges.find((c) => today && c.start_date <= today && c.end_date >= today) ?? challenges[0]
  }, [challenges, selected, meta.data?.today])

  const value: Session = {
    token,
    user: token ? me.data : undefined,
    userLoading: !!token && me.isLoading,
    meta: meta.data,
    challenges,
    challengesLoading: !!token && mine.isLoading,
    challenge,
    selectChallenge,
    signIn,
    signOut,
  }
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used inside SessionProvider')
  return ctx
}
