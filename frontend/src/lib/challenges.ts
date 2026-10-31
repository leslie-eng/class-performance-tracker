import type { ChallengeStatus, ProposalInput } from './types'
import { addDays, daysBetween } from './dates'

/** Same limits the API enforces (app/schemas_challenges.py); checked here so the form can say why early. */
export const MAX_CHALLENGE_DAYS = 366
export const NAME_MIN = 3

export type ProposalErrors = Partial<Record<keyof ProposalInput, string>>

/**
 * Field errors for a proposal, or {} when it's valid. `today` is the server's date (from /meta),
 * so a member in another timezone sees the same rule the API applies.
 */
export function validateProposal(p: ProposalInput, today: string, startChanged = true): ProposalErrors {
  const errors: ProposalErrors = {}
  const name = p.name.trim()
  if (name.length < NAME_MIN) errors.name = `Give it a name of at least ${NAME_MIN} characters`
  else if (name.length > 200) errors.name = 'Keep the name under 200 characters'
  if ((p.description ?? '').length > 2000) errors.description = 'Keep the description under 2,000 characters'
  if (!p.start_date) errors.start_date = 'Pick a start date'
  else if (startChanged && p.start_date < today) errors.start_date = "The start date can't be in the past"
  if (!p.end_date) errors.end_date = 'Pick an end date'
  else if (p.start_date && p.end_date < p.start_date) errors.end_date = 'The end date must be on or after the start date'
  else if (p.start_date && daysBetween(p.start_date, p.end_date) + 1 > MAX_CHALLENGE_DAYS)
    errors.end_date = `A challenge can last at most ${MAX_CHALLENGE_DAYS} days`
  return errors
}

export function emptyProposal(today: string): ProposalInput {
  return { name: '', description: '', start_date: addDays(today, 1), end_date: addDays(today, 30), task_types_allowed: 'both' }
}

export const TASK_LABELS = { both: 'code + articles', code: 'code only', article: 'articles only' } as const

export const STATUS_BADGE: Record<ChallengeStatus, { label: string; icon: string; className: string }> = {
  pending: { label: 'Pending review', icon: 'hourglass_top', className: 'bg-tertiary-fixed text-tertiary' },
  approved: { label: 'Approved', icon: 'check_circle', className: 'bg-secondary-container text-on-secondary-container' },
  rejected: { label: 'Not approved', icon: 'cancel', className: 'bg-error-container text-on-error-container' },
  cancelled: { label: 'Cancelled', icon: 'block', className: 'bg-surface-container text-on-surface-variant' },
}

/** What a member may still do with their own proposal (the API enforces the same rule). */
export function canEditOrCancel(status: ChallengeStatus): boolean {
  return status === 'pending'
}
