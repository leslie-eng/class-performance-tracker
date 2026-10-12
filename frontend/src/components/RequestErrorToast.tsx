import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { ErrorBanner, Icon } from './ui'

let show: (err: unknown) => void = (err: unknown) => {
  pendingError = err
}
let pendingError: unknown = null

/**
 * QueryCache onError hook for failed data loads. Mutations show their own inline ErrorBanner;
 * without this, a failed load (e.g. /auth/me blocked by CORS) just leaves a spinner on screen.
 */
export function reportQueryError(err: unknown) {
  if (err instanceof ApiError && err.status === 401) return // session expired: signOut handles it
  show(err)
}

export function RequestErrorToast() {
  const qc = useQueryClient()
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    show = setError
    // Flush any error reported before mount
    if (pendingError) {
      setError(pendingError)
      pendingError = null
    }
    return () => {
      show = (err) => {
        pendingError = err
      }
    }
  }, [])

  if (!error) return null
  return (
    <div className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-lg flex-col gap-2 rounded-xl bg-surface p-3 shadow-modal">
      <ErrorBanner error={error} />
      <div className="flex justify-end gap-2 text-label-md">
        <button
          type="button"
          className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-primary hover:bg-surface-container-low"
          onClick={() => {
            setError(null)
            qc.refetchQueries({ type: 'active' })
          }}
        >
          <Icon name="refresh" className="text-[18px]" />
          Retry
        </button>
        <button
          type="button"
          className="rounded-lg px-3 py-1.5 text-on-surface-variant hover:bg-surface-container-low"
          onClick={() => setError(null)}
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
