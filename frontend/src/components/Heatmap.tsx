import { addDays, parseDay, shortDate } from '../lib/dates'
import type { Challenge, SubmissionType } from '../lib/types'

const WEEKDAY_LABELS = ['Mon', '', 'Wed', '', 'Fri', '', '']

/** GitHub-style contribution grid over the whole challenge window (7 rows = Mon..Sun). */
export function Heatmap({
  challenge,
  today,
  done,
}: {
  challenge: Challenge
  today: string
  done: Map<string, SubmissionType>
}) {
  // Pad the first column back to Monday.
  const startWeekday = (parseDay(challenge.start_date).getUTCDay() + 6) % 7
  const gridStart = addDays(challenge.start_date, -startWeekday)
  const cells = startWeekday + challenge.total_days
  const weeks = Math.ceil(cells / 7)

  const columns = Array.from({ length: weeks }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => addDays(gridStart, w * 7 + d)),
  )

  let lastMonth = -1
  const monthLabels = columns.map((col) => {
    const first = col.find((d) => d >= challenge.start_date && d <= challenge.end_date)
    if (!first) return ''
    const m = parseDay(first).getUTCMonth()
    if (m === lastMonth) return ''
    lastMonth = m
    return parseDay(first).toLocaleDateString(undefined, { month: 'short', timeZone: 'UTC' })
  })

  function cellClass(d: string): string {
    if (d < challenge.start_date || d > challenge.end_date) return 'invisible'
    const type = done.get(d)
    if (type === 'article') return 'bg-heat-4'
    if (type === 'code') return 'bg-heat-3'
    if (d > today) return 'bg-surface-container-low'
    if (d === today) return 'bg-heat-0 ring-2 ring-primary-container/50'
    return 'bg-heat-0'
  }

  function cellTitle(d: string): string {
    const type = done.get(d)
    if (type) return `${shortDate(d)}: ${type} task done`
    if (d > today) return `${shortDate(d)}: upcoming`
    if (d === today) return `${shortDate(d)}: today, not yet submitted`
    return `${shortDate(d)}: missed`
  }

  return (
    <div className="overflow-x-auto pb-1">
      <div
        className="grid gap-[3px]"
        style={{ gridTemplateColumns: `28px repeat(${weeks}, minmax(12px, 1fr))`, maxWidth: 28 + weeks * 27 }}
      >
        <span />
        {monthLabels.map((m, i) => (
          <span key={i} className="h-4 overflow-visible font-mono text-label-sm whitespace-nowrap text-on-surface-variant">
            {m}
          </span>
        ))}
        {Array.from({ length: 7 }, (_, row) => (
          <Row key={row} label={WEEKDAY_LABELS[row]!}>
            {columns.map((col) => {
              const d = col[row]!
              return <span key={d} title={cellTitle(d)} className={`aspect-square w-full rounded-[3px] ${cellClass(d)}`} />
            })}
          </Row>
        ))}
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <span className="flex items-center pr-1 font-mono text-[10px] text-on-surface-variant">{label}</span>
      {children}
    </>
  )
}

export function HeatmapLegend() {
  return (
    <div className="flex items-center gap-3 font-mono text-label-sm text-on-surface-variant">
      <span className="flex items-center gap-1">
        <span className="h-2.5 w-2.5 rounded-[3px] bg-heat-0" /> Missed
      </span>
      <span className="flex items-center gap-1">
        <span className="h-2.5 w-2.5 rounded-[3px] bg-heat-3" /> Code
      </span>
      <span className="flex items-center gap-1">
        <span className="h-2.5 w-2.5 rounded-[3px] bg-heat-4" /> Article
      </span>
    </div>
  )
}
