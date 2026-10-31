import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { relativeTime } from '../lib/dates'
import { keys, useInbox, useUnreadCount } from '../lib/queries'
import type { InboxItem } from '../lib/types'
import { ErrorBanner, Icon, Spinner } from './ui'

/** In-app notifications (GET /inbox). The badge polls a cheap count; the list loads when opened. */
export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const unread = useUnreadCount().data?.unread ?? 0
  const inbox = useInbox(open)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      buttonRef.current?.focus()
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const refresh = () => qc.invalidateQueries({ queryKey: keys.inbox }) // the list and the badge
  const markRead = useMutation({ mutationFn: (id: number) => api<InboxItem>(`/inbox/${id}/read`, { method: 'POST' }), onSuccess: refresh })
  const markAll = useMutation({ mutationFn: () => api<{ unread: number }>('/inbox/read-all', { method: 'POST' }), onSuccess: refresh })

  function openItem(m: InboxItem) {
    if (!m.read_at) markRead.mutate(m.id)
    setOpen(false)
    if (m.link) navigate(m.link)
  }

  const items = inbox.data?.items ?? []
  return (
    <div ref={ref} className="relative">
      <button
        ref={buttonRef}
        className="btn-ghost relative h-9 px-2"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
      >
        <Icon name="notifications" />
        {unread > 0 && (
          <span aria-hidden className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-error px-1 font-mono text-[10px] text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute top-full right-0 z-[55] mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-xl bg-surface-container-lowest p-1 shadow-modal">
          <div className="flex items-center justify-between px-3 py-2">
            <p className="font-medium text-ink">Notifications</p>
            {unread > 0 && (
              <button className="text-body-sm text-primary-container hover:underline" onClick={() => markAll.mutate()} disabled={markAll.isPending}>
                Mark all read
              </button>
            )}
          </div>
          <div className="px-2">
            <ErrorBanner error={inbox.error ?? markAll.error} />
          </div>
          {inbox.isLoading ? (
            <p role="status" className="flex items-center gap-2 px-3 py-4 text-body-sm text-on-surface-variant">
              <Spinner /> Loading…
            </p>
          ) : items.length === 0 ? (
            <p className="px-3 py-4 text-body-sm text-on-surface-variant">You're all caught up.</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {items.map((m) => (
                <li key={m.id}>
                  <button
                    className={`flex w-full gap-2 rounded-lg px-3 py-2 text-left hover:bg-surface-container-low ${m.read_at ? '' : 'bg-primary-fixed/40'}`}
                    onClick={() => openItem(m)}
                  >
                    <span aria-hidden className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${m.read_at ? 'bg-transparent' : 'bg-primary-container'}`} />
                    <span className="min-w-0">
                      <span className="block font-medium text-ink">
                        {m.title}
                        {!m.read_at && <span className="sr-only"> (unread)</span>}
                      </span>
                      <span className="block text-body-sm text-on-surface-variant">{m.body}</span>
                      <span className="block font-mono text-label-sm text-on-surface-variant">{relativeTime(m.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
