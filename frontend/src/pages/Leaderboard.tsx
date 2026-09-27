import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Avatar, EmptyState, Icon, PageLoader, ProgressBar } from '../components/ui'
import { downloadCsv } from '../lib/format'
import { elapsedDays } from '../lib/dates'
import { useLeaderboard } from '../lib/queries'
import { useSession } from '../lib/session'
import type { LeaderboardRow } from '../lib/types'

const PAGE = 10

export default function LeaderboardPage() {
  const { user, challenge, meta } = useSession()
  const [scope, setScope] = useState<'challenge' | 'global'>('challenge')
  const [page, setPage] = useState(0)
  const board = useLeaderboard(scope === 'global' ? 'global' : challenge?.id)

  if (!challenge || !meta || !user || board.isLoading) return <PageLoader />

  const rows = board.data ?? []
  const elapsed = scope === 'challenge' ? elapsedDays(challenge, meta.today) : null
  const me = rows.find((r) => r.user_id === user.id)
  const ahead = me ? rows.filter((r) => r.total_points > me.total_points).at(-1) : undefined
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const shown = rows.slice(page * PAGE, page * PAGE + PAGE)
  const avgStreak = rows.length ? rows.reduce((s, r) => s + r.current_streak, 0) / rows.length : 0
  const activeCount = rows.filter((r) => r.current_streak > 0).length
  const title = scope === 'global' ? 'All challenges' : challenge.name

  function exportCsv() {
    downloadCsv(`leaderboard-${scope === 'global' ? 'global' : challenge!.id}.csv`, [
      ['rank', 'name', 'total_points', 'current_streak', 'longest_streak', 'days_completed', 'avg_ai_score'],
      ...rows.map((r) => [r.rank, r.name, r.total_points, r.current_streak, r.longest_streak, r.days_completed, r.avg_ai_score]),
    ])
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="flex flex-wrap items-center gap-3 text-[28px] leading-tight font-bold tracking-tight text-ink md:text-headline-xl">
            Cohort Leaderboard
            <span className="pill bg-secondary-container font-bold text-on-secondary-container uppercase">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-secondary" /> Live standings
            </span>
          </h1>
          <p className="mt-1 text-body-md text-on-surface-variant">
            Ranking for <b className="text-ink">{title}</b> · {rows.length} {rows.length === 1 ? 'member' : 'members'} · ties broken by current streak
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg bg-surface-container-low p-1 text-body-sm">
            {(['challenge', 'global'] as const).map((s) => (
              <button
                key={s}
                className={`rounded-md px-3 py-1.5 transition-colors ${scope === s ? 'bg-white font-medium text-primary-container shadow-card' : 'text-on-surface-variant hover:text-ink'}`}
                onClick={() => {
                  setScope(s)
                  setPage(0)
                }}
              >
                {s === 'challenge' ? 'This challenge' : 'All-time (global)'}
              </button>
            ))}
          </div>
          <button className="btn-secondary h-9" onClick={exportCsv} disabled={!rows.length}>
            <Icon name="download" className="text-[18px]" /> Export
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="card">
          <EmptyState icon="leaderboard" title="No one on the board yet">
            Standings appear once members join and submit tasks.
          </EmptyState>
        </div>
      ) : (
        <>
          <Podium rows={rows.slice(0, 3)} meId={user.id} />

          {me && (
            <section className="flex flex-col gap-4 rounded-2xl bg-surface-container-low p-5 shadow-card sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-4">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary-container text-white">
                  <Icon name="trending_up" />
                </span>
                <div>
                  <p className="text-headline-md text-ink">
                    You are rank #{me.rank} ({user.name})
                  </p>
                  <p className="text-body-md text-on-surface-variant">
                    {me.rank === 1 ? (
                      "You're at the top. Keep submitting to hold the lead."
                    ) : ahead ? (
                      <>
                        Only <b className="font-mono text-primary-container">{ahead.total_points - me.total_points + 1} pts</b> needed to overtake{' '}
                        {ahead.name} for <b className="text-ink">rank #{ahead.rank}</b>.
                      </>
                    ) : (
                      'You are tied on points; a longer current streak breaks the tie.'
                    )}
                  </p>
                </div>
              </div>
              {scope === 'challenge' && (
                <Link to="/submit" className="btn-primary shrink-0">
                  Submit today's task
                </Link>
              )}
            </section>
          )}

          <section className="card overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4">
              <h2 className="text-headline-md text-ink">Standings</h2>
              <span className="font-mono text-label-sm text-on-surface-variant">auto-refreshes every minute</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left md:min-w-[640px]">
                <thead className="bg-surface-container-low">
                  <tr className="font-mono text-label-sm tracking-wider text-on-surface-variant uppercase">
                    <th className="py-3 pr-2 pl-4 font-medium sm:px-6">Rank</th>
                    <th className="px-3 py-3 font-medium">Student</th>
                    <th className="px-2 py-3 font-medium sm:px-3">Streak</th>
                    <th className="hidden px-3 py-3 font-medium md:table-cell">Tasks completed</th>
                    <th className="hidden px-3 py-3 font-medium sm:table-cell">Avg AI score</th>
                    <th className="py-3 pr-4 pl-2 text-right font-medium sm:px-6">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <StandingRow key={r.user_id} r={r} isMe={r.user_id === user.id} elapsed={elapsed} />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t border-slate-100 px-6 py-3 text-body-sm text-on-surface-variant">
              <span>
                Showing <b className="text-ink">{shown.length}</b> of <b className="text-ink">{rows.length}</b> members
              </span>
              {pages > 1 && (
                <span className="flex items-center gap-2">
                  <button className="btn-ghost h-8 px-3" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                    Previous
                  </button>
                  <span className="font-mono">
                    {page + 1} / {pages}
                  </span>
                  <button className="btn-secondary h-8 px-3" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>
                    Next
                  </button>
                </span>
              )}
            </div>
          </section>

          <section className="flex flex-col gap-2 rounded-2xl bg-surface-container-low p-5 text-body-md text-on-surface-variant sm:flex-row sm:items-center sm:gap-6">
            <span className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-streak-bg text-streak">
                <Icon name="insights" />
              </span>
              Average current streak: <b className="font-mono text-streak-text">{avgStreak.toFixed(1)} days</b>
            </span>
            <span className="hidden sm:inline">•</span>
            <span>
              Members on an active streak: <b className="font-mono text-secondary">{activeCount} / {rows.length}</b>
            </span>
          </section>
        </>
      )}
    </div>
  )
}

const PODIUM = {
  1: { ring: 'ring-[#f59e0b]', block: 'h-44 bg-gradient-to-b from-[#fde68a] to-[#fbbf24]', text: 'text-[#92400e]', label: 'Leader', icon: 'workspace_premium' },
  2: { ring: 'ring-[#94a3b8]', block: 'h-32 bg-gradient-to-b from-[#e2e8f0] to-[#cbd5e1]', text: 'text-slate-600', label: 'Runner up', icon: 'military_tech' },
  3: { ring: 'ring-[#d97706]', block: 'h-24 bg-gradient-to-b from-[#fef3c7] to-[#fcd34d]', text: 'text-[#92400e]', label: 'Third', icon: 'military_tech' },
} as const

function Podium({ rows, meId }: { rows: LeaderboardRow[]; meId: number }) {
  // Visual order: 2nd, 1st, 3rd. Use list position so shared ranks still fill the podium.
  const order = [rows[1], rows[0], rows[2]]
  return (
    <section className="rounded-2xl bg-gradient-to-br from-surface-container-low via-surface-container-low to-tertiary-fixed/40 px-4 pt-10 shadow-card">
      <div className="mx-auto grid max-w-3xl grid-cols-3 items-end gap-3 sm:gap-5">
        {order.map((r, i) => {
          if (!r) return <div key={i} />
          const place = (i === 1 ? 1 : i === 0 ? 2 : 3) as 1 | 2 | 3
          const s = PODIUM[place]
          return (
            <div key={r.user_id} className="flex flex-col items-center text-center">
              <div className="relative mb-3">
                {place === 1 && <Icon name="workspace_premium" filled className="absolute -top-7 left-1/2 -translate-x-1/2 text-[28px] text-streak" />}
                <Avatar name={r.name} id={r.user_id} size={place === 1 ? 84 : 68} ring={`ring-4 ${s.ring} ring-offset-2`} />
                <span className={`pill absolute -bottom-2 left-1/2 -translate-x-1/2 bg-white font-bold whitespace-nowrap shadow-card ${s.text}`}>
                  #{r.rank}
                </span>
              </div>
              <p className="mt-1 max-w-full truncate text-body-lg font-semibold text-ink sm:text-headline-md">
                {r.name}
                {r.user_id === meId && <span className="ml-1 text-body-sm text-primary-container">(you)</span>}
              </p>
              <p className="mb-3 flex flex-wrap items-center justify-center gap-2">
                <span className="pill bg-streak-bg text-streak-text">
                  <Icon name="local_fire_department" filled className="text-[14px] text-streak" /> {r.current_streak}d
                </span>
                <span className="font-mono text-label-md text-primary-container">{r.total_points.toLocaleString()} pts</span>
              </p>
              <div className={`flex w-full flex-col items-center justify-center rounded-t-xl ${s.block} shadow-card`}>
                <span className={`font-mono text-[40px] leading-none font-bold ${s.text}`}>{place}</span>
                <span className={`font-mono text-label-sm tracking-widest uppercase ${s.text}`}>{s.label}</span>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function StandingRow({ r, isMe, elapsed }: { r: LeaderboardRow; isMe: boolean; elapsed: number | null }) {
  const pct = elapsed ? Math.round((r.days_completed / elapsed) * 100) : null
  const rankTint = r.rank === 1 ? 'bg-streak-bg text-streak-text' : r.rank === 2 ? 'bg-slate-100 text-slate-600' : r.rank === 3 ? 'bg-tertiary-fixed text-tertiary' : 'text-on-surface-variant'
  return (
    <tr className={`border-t border-slate-100 ${isMe ? 'bg-primary-fixed/40 shadow-[inset_4px_0_0_#2563eb]' : 'hover:bg-surface-container-low/60'}`}>
      <td className="py-3.5 pr-2 pl-4 sm:px-6">
        <span className="flex items-center gap-2">
          <span className={`inline-flex h-8 min-w-8 items-center justify-center rounded-full px-1.5 font-mono text-label-md font-bold ${rankTint}`}>#{r.rank}</span>
          {isMe && <span className="hidden rounded bg-primary-container sm:inline px-1.5 py-0.5 font-mono text-[10px] font-bold text-white">YOU</span>}
        </span>
      </td>
      <td className="px-2 py-3.5 sm:px-3">
        <span className="flex min-w-0 items-center gap-3">
          <span className="hidden sm:inline-flex">
            <Avatar name={r.name} id={r.user_id} size={34} />
          </span>
          <span className={`font-medium ${isMe ? 'text-primary-container' : 'text-ink'}`}>{r.name}</span>
        </span>
      </td>
      <td className="px-2 py-3.5 sm:px-3">
        <span className={`pill whitespace-nowrap ${r.current_streak > 0 ? 'bg-streak-bg text-streak-text' : 'bg-surface-container-low text-on-surface-variant'}`}>
          <Icon name="local_fire_department" filled={r.current_streak > 0} className="text-[14px]" /> {r.current_streak}<span className="hidden sm:inline"> Days</span>
        </span>
      </td>
      <td className="hidden px-3 py-3.5 md:table-cell">
        {elapsed ? (
          <div className="w-32">
            <div className="mb-1 flex justify-between font-mono text-label-sm">
              <span>
                {r.days_completed}/{elapsed}
              </span>
              <span className="text-primary-container">{pct}%</span>
            </div>
            <ProgressBar value={pct ?? 0} className={pct === 100 ? 'bg-secondary' : 'bg-primary-container'} />
          </div>
        ) : (
          <span className="font-mono text-label-md">{r.days_completed} days</span>
        )}
      </td>
      <td className="hidden px-3 py-3.5 font-mono text-label-md sm:table-cell">
        {r.avg_ai_score !== null ? (
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-secondary" />
            {r.avg_ai_score.toFixed(1)} <span className="text-on-surface-variant">/10</span>
          </span>
        ) : (
          <span className="text-on-surface-variant">–</span>
        )}
      </td>
      <td className={`py-3.5 pr-4 pl-2 text-right font-mono whitespace-nowrap sm:px-6 text-label-md font-bold ${isMe ? 'text-primary-container' : 'text-ink'}`}>
        {r.total_points.toLocaleString()} pts
      </td>
    </tr>
  )
}
