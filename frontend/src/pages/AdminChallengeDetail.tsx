import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DecisionModal, type Decision } from '../components/admin/ChallengeReview'
import { ChallengeStatusBadge } from '../components/ChallengeStatusBadge'
import { EmptyState, ErrorBanner, Icon, PageLoader } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { TASK_LABELS } from '../lib/challenges'
import { shortDate } from '../lib/dates'
import { keys } from '../lib/queries'
import type { AdminChallenge } from '../lib/types'

const when = (iso: string) => new Date(iso).toLocaleString()

/** One challenge with its audit trail: who proposed it, edits, and who reviewed it, when and why. */
export default function AdminChallengeDetailPage() {
  const { id } = useParams()
  const qc = useQueryClient()
  const [deciding, setDeciding] = useState<Decision | null>(null)
  const detail = useQuery({
    queryKey: [...keys.adminChallenges, 'detail', Number(id)],
    queryFn: () => api<AdminChallenge>(`/admin/challenges/${id}`),
  })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.adminChallenges })
    qc.invalidateQueries({ queryKey: keys.challenges })
  }

  if (detail.isLoading) return <PageLoader />
  const c = detail.data
  const back = (
    <Link to="/admin/challenges" className="flex w-fit items-center gap-1 text-body-md text-primary-container hover:underline">
      <Icon name="arrow_back" className="text-[18px]" /> Challenge approvals
    </Link>
  )
  if (!c) {
    const missing = detail.error instanceof ApiError && detail.error.status === 404
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {back}
        {missing ? (
          <div className="card">
            <EmptyState icon="search_off" title="Challenge not found" />
          </div>
        ) : (
          <ErrorBanner error={detail.error} />
        )}
      </div>
    )
  }

  const edited = new Date(c.updated_at).getTime() - new Date(c.created_at).getTime() > 1000
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      {back}
      <section className="card flex flex-col gap-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="text-headline-lg text-ink">{c.name}</h1>
          <ChallengeStatusBadge status={c.status} />
        </div>
        {c.description && <p className="text-body-md text-on-surface-variant">{c.description}</p>}
        <dl className="grid gap-x-6 gap-y-2 text-body-md sm:grid-cols-[auto_1fr]">
          <dt className="text-on-surface-variant">Dates</dt>
          <dd className="text-ink">{shortDate(c.start_date)} → {shortDate(c.end_date)} · {c.total_days} days</dd>
          <dt className="text-on-surface-variant">Tasks</dt>
          <dd className="text-ink">{TASK_LABELS[c.task_types_allowed]}</dd>
          <dt className="text-on-surface-variant">Members joined</dt>
          <dd className="text-ink">{c.enrolled}</dd>
        </dl>
        {c.status === 'pending' && (
          <div className="flex justify-end gap-2">
            <button className="btn-ghost text-error" onClick={() => setDeciding({ challenge: c, action: 'reject' })}>
              <Icon name="close" className="text-[18px]" /> Reject
            </button>
            <button className="btn-primary" onClick={() => setDeciding({ challenge: c, action: 'approve' })}>
              <Icon name="check" className="text-[18px]" /> Approve
            </button>
          </div>
        )}
      </section>

      <section className="card p-6" aria-labelledby="audit-heading">
        <h2 id="audit-heading" className="text-headline-md text-ink">Audit trail</h2>
        <ol className="mt-4 flex flex-col gap-4 border-l-2 border-surface-container-high pl-4">
          <Event icon="lightbulb" title={c.creator ? `Proposed by ${c.creator.name}` : 'Created before approvals existed'} at={c.created_at} />
          {edited && c.status === 'pending' && <Event icon="edit" title="Last edited by the member" at={c.updated_at} />}
          {c.status === 'cancelled' && <Event icon="block" title="Withdrawn by the member" at={c.updated_at} />}
          {c.status === 'approved' && !c.reviewed_at && (
            <Event icon="history" title="Live before approvals existed (counted as approved)" />
          )}
          {(c.status === 'rejected' || (c.status === 'approved' && c.reviewed_at)) && (
            <Event
              icon={c.status === 'approved' ? 'check_circle' : 'cancel'}
              title={`${c.status === 'approved' ? 'Approved' : 'Rejected'} by ${c.reviewer?.name ?? 'a former admin'}`}
              at={c.reviewed_at}
              note={c.review_note}
              noteLabel={c.status === 'rejected' ? 'Reason' : 'Note'}
            />
          )}
          {c.status === 'pending' && <Event icon="hourglass_top" title="Waiting for an admin's decision" />}
        </ol>
      </section>

      {deciding && (
        <DecisionModal
          decision={deciding}
          onClose={() => setDeciding(null)}
          onDone={(updated) => {
            setDeciding(null)
            qc.setQueryData([...keys.adminChallenges, 'detail', updated.id], updated)
            refresh()
          }}
          onConflict={refresh}
        />
      )}
    </div>
  )
}

function Event({ icon, title, at, note, noteLabel }: { icon: string; title: string; at?: string | null; note?: string | null; noteLabel?: string }) {
  return (
    <li className="relative">
      <span className="absolute top-0.5 -left-[27px] flex h-5 w-5 items-center justify-center rounded-full bg-surface-container-lowest text-primary-container">
        <Icon name={icon} className="text-[16px]" />
      </span>
      <p className="font-medium text-ink">{title}</p>
      {at && <p className="font-mono text-label-sm text-on-surface-variant">{when(at)}</p>}
      {note && (
        <p className="mt-1 text-body-md text-ink">
          <span className="text-on-surface-variant">{noteLabel}:</span> {note}
        </p>
      )}
    </li>
  )
}
