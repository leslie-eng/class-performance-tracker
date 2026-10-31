import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AuditTrail, DecisionModal, type Decision } from '../components/admin/ChallengeReview'
import { ChallengeStatusBadge } from '../components/ChallengeStatusBadge'
import { EmptyState, ErrorBanner, Icon, PageLoader } from '../components/ui'
import { api } from '../lib/api'
import { TASK_LABELS } from '../lib/challenges'
import { relativeTime, shortDate } from '../lib/dates'
import { keys } from '../lib/queries'
import type { AdminChallenge, AdminChallengePage, ChallengeStatus } from '../lib/types'

const PAGE = 10
const FILTERS: { value: ChallengeStatus | 'all'; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'all', label: 'All' },
]
/** Admin queue for member-proposed challenges. The API enforces admin-only and the status rules. */
export default function AdminChallengesPage() {
  const qc = useQueryClient()
  const [status, setStatus] = useState<ChallengeStatus | 'all'>('pending')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [deciding, setDeciding] = useState<Decision | null>(null)
  const [notice, setNotice] = useState('')

  const params = new URLSearchParams({ status, limit: String(PAGE), offset: String(offset), ...(q ? { q } : {}) })
  const page = useQuery({
    queryKey: [...keys.adminChallenges, status, q, offset],
    queryFn: () => api<AdminChallengePage>(`/admin/challenges?${params}`),
    placeholderData: keepPreviousData,
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.adminChallenges })
    qc.invalidateQueries({ queryKey: keys.challenges }) // approved ones now show on /join
  }

  function applySearch(e: FormEvent) {
    e.preventDefault()
    setQ(search.trim())
    setOffset(0)
  }

  if (page.isLoading) return <PageLoader />
  const data = page.data
  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-headline-lg text-ink md:text-[28px]">Challenge approvals</h1>
        <p className="text-body-md text-on-surface-variant">
          Members propose challenges here. Nothing is visible to the group or open to join until you approve it.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Filter by status" className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              role="tab"
              aria-selected={status === f.value}
              className={`rounded-lg px-3 py-1.5 text-body-sm ${status === f.value ? 'bg-primary-container font-medium text-white' : 'text-on-surface-variant hover:bg-surface-container-high'}`}
              onClick={() => {
                setStatus(f.value)
                setOffset(0)
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
        <form onSubmit={applySearch} className="flex gap-2" role="search">
          <label className="sr-only" htmlFor="challenge-search">Search by name</label>
          <input id="challenge-search" className="input h-9 w-56 py-1" placeholder="Search by name" value={search} maxLength={100} onChange={(e) => setSearch(e.target.value)} />
          <button className="btn-secondary h-9">Search</button>
        </form>
      </div>

      <p role="status" aria-live="polite" className={notice ? 'rounded-lg bg-secondary-container px-3 py-2 text-body-md text-on-secondary-container' : 'sr-only'}>
        {notice}
      </p>
      <ErrorBanner error={page.error} />

      {items.length === 0 && !page.error ? (
        <div className="card">
          <EmptyState icon="inbox" title={status === 'pending' && !q ? 'Nothing waiting for review' : 'No challenges match'}>
            {status === 'pending' && !q ? 'New proposals from members will appear here, and you will get a notification.' : 'Try another filter or search.'}
          </EmptyState>
        </div>
      ) : (
        <ul className={`flex flex-col gap-4 ${page.isFetching ? 'opacity-70' : ''}`}>
          {items.map((c) => (
            <ChallengeRow key={c.id} c={c} onDecide={(action) => setDeciding({ challenge: c, action })} />
          ))}
        </ul>
      )}

      {total > PAGE && (
        <nav aria-label="Pages" className="flex items-center justify-between text-body-sm text-on-surface-variant">
          <span>
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <div className="flex gap-2">
            <button className="btn-ghost h-9" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Previous
            </button>
            <button className="btn-ghost h-9" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
              Next
            </button>
          </div>
        </nav>
      )}

      {deciding && (
        <DecisionModal
          decision={deciding}
          onClose={() => setDeciding(null)}
          onDone={(c) => {
            setDeciding(null)
            setNotice(`"${c.name}" was ${c.status}. ${c.creator ? `${c.creator.name} has been notified.` : ''}`)
            refresh()
          }}
          onConflict={refresh}
        />
      )}
    </div>
  )
}

function ChallengeRow({ c, onDecide }: { c: AdminChallenge; onDecide: (action: 'approve' | 'reject') => void }) {
  return (
    <li className="card flex flex-col gap-3 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-headline-md text-ink">
            <Link to={`/admin/challenges/${c.id}`} className="hover:underline">{c.name}</Link>
          </h2>
          <p className="text-body-sm text-on-surface-variant">
            Proposed by {c.creator?.name ?? 'an admin (before approvals)'} · {relativeTime(c.created_at)}
          </p>
        </div>
        <ChallengeStatusBadge status={c.status} />
      </div>
      {c.description && <p className="text-body-md text-on-surface-variant">{c.description}</p>}
      <p className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-label-sm text-on-surface-variant">
        <span>{shortDate(c.start_date)} → {shortDate(c.end_date)} · {c.total_days} days</span>
        <span>{TASK_LABELS[c.task_types_allowed]}</span>
        {c.status === 'approved' && <span>{c.enrolled} joined</span>}
      </p>
      {c.status === 'pending' ? (
        <div className="flex justify-end gap-2">
          <button className="btn-ghost text-error" onClick={() => onDecide('reject')}>
            <Icon name="close" className="text-[18px]" /> Reject
          </button>
          <button className="btn-primary" onClick={() => onDecide('approve')}>
            <Icon name="check" className="text-[18px]" /> Approve
          </button>
        </div>
      ) : (
        <AuditTrail c={c} />
      )}
    </li>
  )
}
