import { createContext, useContext } from 'react'
import type { Challenge, Meta, User } from './types'

/**
 * Shared session shape and hook.
 *
 * These live outside SessionProvider's module so that file exports only the provider
 * component — mixing component and non-component exports there breaks React Fast Refresh
 * (`react(only-export-components)` in oxlint).
 */
export interface Session {
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

/** Non-null only while rendered inside SessionProvider. */
export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
    const ctx = useContext(SessionContext)
    if (!ctx) throw new Error('useSession must be used inside SessionProvider')
    return ctx
}
