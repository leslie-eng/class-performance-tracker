import { ApiError } from './api'

/**
 * Tiny external store for the last failed query, consumed by RequestErrorToast via
 * useSyncExternalStore.
 *
 * It lives outside the toast component on purpose:
 *  - keeping component files to component-only exports preserves React Fast Refresh;
 *  - a module-level store means an error fired before the toast mounts (e.g. a failed
 *    /auth/me on first paint) is still there on mount, instead of waiting on an effect
 *    to flush a buffered value — which would also be a setState-in-effect.
 */

let currentError: unknown = null
const listeners = new Set<() => void>()

function emit() {
    for (const listener of listeners) listener()
}

export function reportQueryError(err: unknown) {
    if (err instanceof ApiError && err.status === 401) return // session expired: signOut handles it
    currentError = err
    emit()
}

/** useSyncExternalStore contract: subscribe, and return the current snapshot. */
export function subscribeToQueryErrors(onChange: () => void): () => void {
    listeners.add(onChange)
    return () => {
        listeners.delete(onChange)
    }
}

export function getQueryError(): unknown {
    return currentError
}

export function clearQueryError() {
    if (currentError === null) return
    currentError = null
    emit()
}
