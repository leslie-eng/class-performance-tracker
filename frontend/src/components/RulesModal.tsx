import type { Challenge } from '../lib/types'
import { Modal } from './ui'

export function RulesModal({ challenge, onClose }: { challenge: Challenge; onClose: () => void }) {
  const r = challenge.effective_rules
  const types = { both: 'Code or article', code: 'Code only', article: 'Articles only' }[challenge.task_types_allowed]
  const rows: [string, string][] = [
    ['Challenge window', `${challenge.start_date} → ${challenge.end_date} (${challenge.total_days} days)`],
    ['Accepted tasks', types],
    ['Code task', `${r.code_points} pts`],
    ['Article task', `${r.article_points} pts + up to ${r.article_ai_bonus_max} AI-grade bonus`],
    ['Streak bonus', `+${r.streak_bonus_points} pts every ${r.streak_bonus_every} days in a row`],
    ['Missed day', r.missed_day_penalty ? `−${r.missed_day_penalty} pts, streak resets` : 'No penalty, but the streak resets'],
    ['Late logging', r.backfill_days ? `Up to ${r.backfill_days} day(s) late` : 'Same day only'],
    ['Extra submissions', 'Allowed, but only the first each day earns points'],
    ['WhatsApp nudge', `After ${r.lag_threshold} missed days (if opted in)`],
  ]
  return (
    <Modal title="Challenge rules" onClose={onClose}>
      {challenge.description && <p className="mb-4 text-body-md text-on-surface-variant">{challenge.description}</p>}
      <dl className="divide-y divide-slate-100">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 py-2.5">
            <dt className="text-body-md text-on-surface-variant">{k}</dt>
            <dd className="text-right text-body-md font-medium text-ink">{v}</dd>
          </div>
        ))}
      </dl>
    </Modal>
  )
}
