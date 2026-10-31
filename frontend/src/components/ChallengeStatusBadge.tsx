import { STATUS_BADGE } from '../lib/challenges'
import type { ChallengeStatus } from '../lib/types'
import { Icon } from './ui'

export function ChallengeStatusBadge({ status }: { status: ChallengeStatus }) {
  const b = STATUS_BADGE[status]
  return (
    <span className={`pill shrink-0 ${b.className}`}>
      <Icon name={b.icon} className="text-[14px]" /> {b.label}
    </span>
  )
}
