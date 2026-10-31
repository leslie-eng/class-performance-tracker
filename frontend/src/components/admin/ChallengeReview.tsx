import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api, ApiError } from '../../lib/api'
import { relativeTime, shortDate } from '../../lib/dates'
import type { AdminChallenge } from '../../lib/types'
import { ErrorBanner, Modal } from '../ui'

export type Decision = { challenge: AdminChallenge; action: 'approve' | 'reject' }

/** Who reviewed it, when and why (Step 5's audit trail). */
export function AuditTrail({ c }: { c: AdminChallenge }) {
  if (c.status === 'cancelled') {
    return <p className="text-body-sm text-on-surface-variant">Withdrawn by the member {relativeTime(c.updated_at)}.</p>
  }
  if (!c.reviewer && !c.reviewed_at) return null
  return (
    <dl className="grid gap-x-4 gap-y-1 rounded-lg bg-surface-container-low px-3 py-2 text-body-sm sm:grid-cols-[auto_1fr]">
      <dt className="text-on-surface-variant">{c.status === 'approved' ? 'Approved by' : 'Rejected by'}</dt>
      <dd className="text-ink">
        {c.reviewer?.name ?? 'a former admin'}
        {c.reviewed_at && <> · {new Date(c.reviewed_at).toLocaleString()}</>}
      </dd>
      {c.review_note && (
        <>
          <dt className="text-on-surface-variant">{c.status === 'rejected' ? 'Reason' : 'Note'}</dt>
          <dd className="text-ink">{c.review_note}</dd>
        </>
      )}
    </dl>
  )
}

export function DecisionModal({
  decision: { challenge, action },
  onClose,
  onDone,
  onConflict,
}: {
  decision: Decision
  onClose: () => void
  onDone: (c: AdminChallenge) => void
  onConflict: () => void
}) {
  const [note, setNote] = useState('')
  const reject = action === 'reject'
  const decide = useMutation({
    mutationFn: () =>
      api<AdminChallenge>(`/admin/challenges/${challenge.id}/${action}`, {
        method: 'POST',
        json: reject ? { note: note.trim() } : { note: note.trim() || null },
      }),
    onSuccess: onDone,
    // 409: another admin (or the member) got there first. Refresh the queue behind the dialog.
    onError: (err) => err instanceof ApiError && err.status === 409 && onConflict(),
  })
  const conflict = decide.error instanceof ApiError && decide.error.status === 409

  return (
    <Modal title={reject ? 'Reject this challenge?' : 'Approve this challenge?'} onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault()
          decide.mutate()
        }}
      >
        <p className="text-body-md text-on-surface-variant">
          {reject
            ? `"${challenge.name}" won't be listed. ${challenge.creator?.name ?? 'The member'} will see your reason.`
            : `"${challenge.name}" (${shortDate(challenge.start_date)} → ${shortDate(challenge.end_date)}) will be listed for everyone to join, with the default scoring rules.`}
        </p>
        <label className="flex flex-col gap-1.5">
          <span className="label">{reject ? 'Reason (required, shown to the member)' : 'Note to the member (optional)'}</span>
          <textarea
            className="input min-h-20"
            maxLength={1000}
            required={reject}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={reject ? 'e.g. It overlaps with 100 Days of Python; try again in January' : 'e.g. Starts Monday, good luck!'}
          />
        </label>
        {conflict ? (
          <div role="alert" className="flex flex-col gap-2 rounded-lg bg-tertiary-fixed px-3 py-2 text-body-md text-tertiary">
            <span>{(decide.error as Error).message}. The list has been refreshed.</span>
          </div>
        ) : (
          <ErrorBanner error={decide.error} />
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose} disabled={decide.isPending}>
            {conflict ? 'Close' : 'Cancel'}
          </button>
          {!conflict && (
            <button className="btn-primary" disabled={decide.isPending || (reject && !note.trim())}>
              {reject ? 'Reject' : 'Approve'}
            </button>
          )}
        </div>
      </form>
    </Modal>
  )
}
