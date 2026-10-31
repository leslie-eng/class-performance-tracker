import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChallengeStatusBadge } from '../components/ChallengeStatusBadge'
import { ProposalForm } from '../components/ProposalForm'
import { EmptyState, ErrorBanner, Icon, Modal, PageLoader } from '../components/ui'
import { api } from '../lib/api'
import { canEditOrCancel, emptyProposal, TASK_LABELS } from '../lib/challenges'
import { relativeTime, shortDate } from '../lib/dates'
import { keys, useMyProposals } from '../lib/queries'
import { useSession } from '../lib/session-context'
import type { Proposal, ProposalInput } from '../lib/types'

function changed(p: Proposal, v: ProposalInput): Partial<ProposalInput> {
  const out: Partial<ProposalInput> = {}
  if (v.name !== p.name) out.name = v.name
  if ((v.description ?? null) !== (p.description ?? null)) out.description = v.description
  if (v.start_date !== p.start_date) out.start_date = v.start_date
  if (v.end_date !== p.end_date) out.end_date = v.end_date
  if (v.task_types_allowed !== p.task_types_allowed) out.task_types_allowed = v.task_types_allowed
  return out
}

/** Members propose challenges here and follow them through review. */
export default function MyChallengesPage() {
  const { meta } = useSession()
  const qc = useQueryClient()
  const proposals = useMyProposals()
  const [editing, setEditing] = useState<Proposal | 'new' | null>(null)
  const [cancelling, setCancelling] = useState<Proposal | null>(null)
  const [notice, setNotice] = useState('')
  const refresh = () => qc.invalidateQueries({ queryKey: keys.proposals })

  const save = useMutation({
    mutationFn: ({ target, values }: { target: Proposal | 'new'; values: ProposalInput }) =>
      target === 'new'
        ? api<Proposal>('/challenges/proposals', { method: 'POST', json: values })
        : api<Proposal>(`/challenges/proposals/${target.id}`, { method: 'PATCH', json: changed(target, values) }),
    onSuccess: (p, { target }) => {
      setEditing(null)
      setNotice(target === 'new' ? `"${p.name}" was sent for review. You'll get a notification when an admin decides.` : `"${p.name}" was updated.`)
      refresh()
    },
    // Someone else (an admin) may have acted meanwhile: show the server's view.
    onError: refresh,
  })
  const cancel = useMutation({
    mutationFn: (p: Proposal) => api<Proposal>(`/challenges/proposals/${p.id}/cancel`, { method: 'POST' }),
    onSuccess: (p) => {
      setCancelling(null)
      setNotice(`"${p.name}" was cancelled.`)
      refresh()
    },
    onError: refresh,
  })

  if (proposals.isLoading || !meta) return <PageLoader />
  const list = proposals.data ?? []

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-headline-lg text-ink md:text-[28px]">My challenge proposals</h1>
          <p className="text-body-md text-on-surface-variant">
            Suggest a challenge for the group. An admin reviews it before anyone can{' '}
            <Link to="/join" className="text-primary-container underline">join</Link>.
          </p>
        </div>
        <button className="btn-primary" onClick={() => { save.reset(); setEditing('new') }}>
          <Icon name="add" className="text-[18px]" /> Propose a challenge
        </button>
      </div>

      {/* Always present, so the confirmation after each action is announced. */}
      <p role="status" aria-live="polite" className={notice ? 'rounded-lg bg-secondary-container px-3 py-2 text-body-md text-on-secondary-container' : 'sr-only'}>
        {notice}
      </p>
      <ErrorBanner error={proposals.error} />

      {list.length === 0 && !proposals.error ? (
        <div className="card">
          <EmptyState icon="lightbulb" title="No proposals yet">
            Have an idea, like "30 Days of SQL"? Propose it and an admin will review it.
          </EmptyState>
        </div>
      ) : (
        <ul className="flex flex-col gap-4">
          {list.map((p) => (
            <li key={p.id} className="card flex flex-col gap-3 p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h2 className="text-headline-md text-ink">{p.name}</h2>
                <ChallengeStatusBadge status={p.status} />
              </div>
              {p.description && <p className="text-body-md text-on-surface-variant">{p.description}</p>}
              <p className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-label-sm text-on-surface-variant">
                <span>{shortDate(p.start_date)} → {shortDate(p.end_date)} · {p.total_days} days</span>
                <span>{TASK_LABELS[p.task_types_allowed]}</span>
                <span>proposed {relativeTime(p.created_at)}</span>
              </p>
              {p.status === 'rejected' && p.review_note && (
                <p className="rounded-lg bg-error-container/60 px-3 py-2 text-body-md text-on-error-container">
                  <span className="font-medium">Reason:</span> {p.review_note}
                </p>
              )}
              {p.status === 'approved' && (
                <p className="text-body-md text-secondary">
                  Approved{p.review_note ? `: ${p.review_note}` : ''}.{' '}
                  <Link to="/join" className="underline">Join it</Link>
                </p>
              )}
              {canEditOrCancel(p.status) && (
                <div className="flex justify-end gap-2">
                  <button className="btn-ghost" onClick={() => { cancel.reset(); setCancelling(p) }}>
                    Cancel proposal
                  </button>
                  <button className="btn-secondary" onClick={() => { save.reset(); setEditing(p) }}>
                    <Icon name="edit" className="text-[18px]" /> Edit
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <Modal title={editing === 'new' ? 'Propose a challenge' : 'Edit proposal'} onClose={() => setEditing(null)}>
          <ProposalForm
            initial={editing === 'new' ? emptyProposal(meta.today) : editing}
            today={meta.today}
            submitLabel={editing === 'new' ? 'Send for review' : 'Save changes'}
            pending={save.isPending}
            error={save.error}
            onSubmit={(values) => save.mutate({ target: editing, values })}
            onCancel={() => setEditing(null)}
          />
        </Modal>
      )}

      {cancelling && (
        <Modal title="Cancel this proposal?" onClose={() => setCancelling(null)}>
          <p className="text-body-md text-on-surface-variant">
            "{cancelling.name}" will be withdrawn from review. You can't undo this, but you can propose it again.
          </p>
          <div className="mt-4 flex flex-col gap-3">
            <ErrorBanner error={cancel.error} />
            <div className="flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setCancelling(null)} disabled={cancel.isPending}>
                Keep it
              </button>
              <button className="btn-primary" onClick={() => cancel.mutate(cancelling)} disabled={cancel.isPending}>
                Cancel proposal
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
