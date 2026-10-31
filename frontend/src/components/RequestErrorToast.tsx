import { useQueryClient } from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'
import { clearQueryError, getQueryError, subscribeToQueryErrors } from '../lib/query-errors'
import { ErrorBanner, Icon } from './ui'

/**
 * Shows failed data loads. Mutations render their own inline ErrorBanner; without this, a
 * failed load (e.g. /auth/me blocked by CORS) just leaves a spinner on screen.
 *
 * State comes from the module store via useSyncExternalStore rather than an effect that
 * calls setState, which caused a cascading render on mount.
 */
export function RequestErrorToast() {
  const qc = useQueryClient()
  const error = useSyncExternalStore(subscribeToQueryErrors, getQueryError, getQueryError)

  if (!error) return null
  return (
    <div className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-lg flex-col gap-2 rounded-xl bg-surface p-3 shadow-modal">
      <ErrorBanner error={error} />
      <div className="flex justify-end gap-2 text-label-md">
        <button
          type="button"
          className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-primary hover:bg-surface-container-low"
          onClick={() => {
            clearQueryError()
            qc.refetchQueries({ type: 'active' })
          }}
        >
          <Icon name="refresh" className="text-[18px]" />
          Retry
        </button>
        <button
          type="button"
          className="rounded-lg px-3 py-1.5 text-on-surface-variant hover:bg-surface-container-low"
          onClick={clearQueryError}
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
