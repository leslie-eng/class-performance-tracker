import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Heatmap, HeatmapLegend } from '../components/Heatmap'
import { RulesModal } from '../components/RulesModal'
import { EmptyState, Icon, PageLoader, ProgressBar, ScoreRing, StatCard } from '../components/ui'
import { addDays, dateForDay, dayNumber, formatCountdown, greeting, parseDay, relativeTime } from '../lib/dates'
import { useCountdown } from '../lib/useCountdown'
import { useLeaderboard, useMySubmissions } from '../lib/queries'
import { useSession } from '../lib/session'
import { submissionTitle } from '../lib/submissions'
import type { Challenge, Submission, SubmissionType } from '../lib/types'

export default function DashboardPage() {
  const { user, challenge, meta } = useSession()
  const subs = useMySubmissions(challenge?.id)
  const board = useLeaderboard(challenge?.id)
  const [showRules, setShowRules] = useState(false)

  const done = useMemo(() => {
    const m = new Map<string, SubmissionType>()
    for (const s of subs.data ?? []) {
      if (!s.counts_for_streak || !challenge) continue
      const d = dateForDay(challenge, s.day_number)
      if (m.get(d) !== 'article') m.set(d, s.submission_type)
    }
    return m
  }, [subs.data, challenge])

  if (!challenge || !meta || !user || subs.isLoading || board.isLoading) return <PageLoader />

  const today = meta.today
  const rules = challenge.effective_rules
  const day = dayNumber(challenge, today)
  const inWindow = day >= 1 && day <= challenge.total_days
  const submittedToday = done.has(today)
  const me = board.data?.find((r) => r.user_id === user.id)
  const rows = board.data ?? []
  const ahead = me ? rows.filter((r) => r.total_points > me.total_points).at(-1) : undefined
  const streak = me?.current_streak ?? 0
  const all = subs.data ?? []
  const weekAgo = addDays(today, -6)
  const pointsThisWeek = all
    .filter((s) => s.counts_for_streak && dateForDay(challenge, s.day_number) >= weekAgo)
    .reduce((sum, s) => sum + s.points_awarded, 0)
  const toBonus = rules.streak_bonus_every - (streak % rules.streak_bonus_every)
  const completedPct = Math.round(((me?.days_completed ?? 0) / challenge.total_days) * 100)
  const latestGraded = all.find((s) => s.submission_type === 'article' && s.grading_status === 'done' && s.ai_score !== null)

  return (
    <div className="flex flex-col gap-6">
      {/* Hero */}
      <section className="card flex flex-col gap-5 p-6 md:flex-row md:items-center md:justify-between md:p-7">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="pill bg-primary-fixed text-primary-container uppercase">{challenge.name}</span>
            <span className="flex items-center gap-1.5 text-body-md text-on-surface-variant">
              <span className="h-1.5 w-1.5 rounded-full bg-secondary" />
              {inWindow ? `Day ${day} of ${challenge.total_days}` : day < 1 ? `Starts ${challenge.start_date}` : 'Challenge ended'}
            </span>
          </div>
          <h1 className="mt-2 text-headline-lg text-ink md:text-[28px] md:leading-9">
            {greeting(meta.timezone)}, {user.name.split(' ')[0]}!{' '}
            {inWindow && (submittedToday ? "Today's task is in." : streak > 0 ? 'Keep the streak alive today.' : "Let's get today's task in.")}
          </h1>
          <p className="mt-1 text-body-md text-on-surface-variant">
            {!inWindow
              ? day < 1
                ? 'The challenge has not started yet. You can submit from day 1.'
                : 'This challenge is over. Your final standings are below.'
              : submittedToday
                ? `Nice work. Come back tomorrow for day ${day + 1}.`
                : `Submit day ${day} before midnight (${meta.timezone}) to ${streak > 0 ? `keep your ${streak}-day streak` : 'start a new streak'}.`}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-3">
          <button className="btn-secondary" onClick={() => setShowRules(true)}>
            <Icon name="menu_book" className="text-[20px]" /> View Rules
          </button>
          {inWindow && !submittedToday && (
            <Link to="/submit" className="btn-primary">
              <Icon name="task_alt" className="text-[20px]" /> Submit Today's Task
            </Link>
          )}
        </div>
      </section>

      {/* Stats */}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Current Streak" icon="local_fire_department" iconClass="bg-streak-bg text-streak">
          <p>
            <span className="font-mono text-[40px] leading-none font-bold text-ink">{streak}</span>
            <span className="ml-1.5 font-mono text-on-surface-variant">{streak === 1 ? 'day' : 'days'}</span>
          </p>
          <p className="text-body-sm text-on-surface-variant">
            {toBonus === rules.streak_bonus_every && streak > 0
              ? `Streak bonus earned! Next one in ${rules.streak_bonus_every} days.`
              : `${toBonus} more ${toBonus === 1 ? 'day' : 'days'} to a +${rules.streak_bonus_points} pt streak bonus`}
          </p>
        </StatCard>
        <StatCard label="Longest Streak" icon="emoji_events" iconClass="bg-primary-fixed text-primary-container">
          <p>
            <span className="font-mono text-[40px] leading-none font-bold text-ink">{me?.longest_streak ?? 0}</span>
            <span className="ml-1.5 font-mono text-on-surface-variant">days</span>
          </p>
          {me && me.longest_streak > 0 && me.longest_streak === streak ? (
            <span className="pill w-fit bg-primary-fixed text-primary-container">Personal record, live</span>
          ) : (
            <p className="text-body-sm text-on-surface-variant">Your best run in this challenge</p>
          )}
        </StatCard>
        <StatCard label="Points" icon="bolt" iconClass="bg-secondary-container text-secondary">
          <p className="flex items-baseline gap-2">
            <span className="font-mono text-[40px] leading-none font-bold text-ink">{(me?.total_points ?? 0).toLocaleString()}</span>
            {pointsThisWeek > 0 && <span className="font-mono text-label-md text-secondary">+{pointsThisWeek} this wk</span>}
          </p>
          <ProgressBar value={completedPct} />
          <p className="flex justify-between font-mono text-label-sm text-on-surface-variant">
            <span>
              {me?.days_completed ?? 0}/{challenge.total_days} days
            </span>
            <span className="text-primary-container">{completedPct}%</span>
          </p>
        </StatCard>
        <StatCard label="Cohort Standing" icon="leaderboard" iconClass="bg-surface-container text-on-surface">
          <p className="flex items-baseline gap-1.5">
            <span className="font-mono text-[40px] leading-none font-bold text-ink">#{me?.rank ?? '–'}</span>
            <span className="font-mono text-on-surface-variant">/ {rows.length} members</span>
          </p>
          <p className="text-body-sm text-on-surface-variant">
            {me?.rank === 1
              ? "You're leading the cohort."
              : ahead && me
                ? `${ahead.total_points - me.total_points} pts behind ${ahead.name.split(' ')[0]} (#${ahead.rank})`
                : 'Submit tasks to climb the board.'}
          </p>
        </StatCard>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-6">
          {/* Activity */}
          <section className="card p-6">
            <div className="mb-5">
              <h2 className="flex items-center gap-2 text-headline-md text-ink">
                <Icon name="grid_view" className="text-primary-container" /> Activity Log
              </h2>
              <p className="text-body-md text-on-surface-variant">Every day of {challenge.name}, from day 1 to day {challenge.total_days}.</p>
            </div>
            <Heatmap challenge={challenge} today={today} done={done} />
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <span className="text-body-md text-ink">
                {me?.days_completed ?? 0} of {challenge.total_days} days completed{' '}
                <span className="pill ml-1 bg-primary-fixed text-primary-container">{completedPct}%</span>
              </span>
              <HeatmapLegend />
            </div>
          </section>

          {/* Recent submissions */}
          <section className="card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-headline-md text-ink">
                <Icon name="history" className="text-primary-container" /> Recent Submissions
              </h2>
              {all.length > 0 && <span className="font-mono text-label-md text-on-surface-variant">{all.length} total</span>}
            </div>
            {all.length === 0 ? (
              <EmptyState icon="task_alt" title="No submissions yet">
                Your submitted tasks and their AI feedback will appear here.
              </EmptyState>
            ) : (
              <ul className="flex flex-col gap-3">
                {all.slice(0, 6).map((s) => (
                  <SubmissionRow key={s.id} s={s} />
                ))}
              </ul>
            )}
          </section>

          {latestGraded && <GraderInsight s={latestGraded} />}
        </div>

        <aside className="flex flex-col gap-6">
          <TodayCard challenge={challenge} day={day} inWindow={inWindow} submitted={submittedToday} timezone={meta.timezone} />
          <WeekCard today={today} done={done} challenge={challenge} />
          <MilestoneCard streak={streak} every={rules.streak_bonus_every} bonus={rules.streak_bonus_points} />
        </aside>
      </div>

      {showRules && <RulesModal challenge={challenge} onClose={() => setShowRules(false)} />}
    </div>
  )
}

function SubmissionRow({ s }: { s: Submission }) {
  const isArticle = s.submission_type === 'article'
  const status =
    s.grading_status === 'pending' ? (
      <span className="flex items-center gap-1 text-primary-container">
        <Icon name="hourglass_top" className="text-[14px]" /> Grading…
      </span>
    ) : s.grading_status === 'failed' ? (
      <span className="text-error">Grading failed</span>
    ) : isArticle && s.ai_score !== null ? (
      <span className="text-secondary">Graded ({s.ai_score}/10)</span>
    ) : (
      <span className="text-secondary">Logged ✓</span>
    )
  const body = (
    <div className="flex items-center gap-4 rounded-xl bg-surface-container-low p-4 transition-shadow hover:shadow-lift">
      <span className={`flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-lg font-mono text-label-md font-bold ${isArticle ? 'bg-tertiary-fixed text-tertiary' : 'bg-primary-fixed text-primary-container'}`}>
        D{s.day_number}
        <Icon name={isArticle ? 'article' : 'code'} className="text-[16px]" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{submissionTitle(s)}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-body-sm text-on-surface-variant">
          <span className="rounded bg-white px-1.5 py-0.5 font-mono">{isArticle ? 'Article' : (s.language ?? 'Code')}</span>
          <span>{relativeTime(s.submitted_at)}</span>
          <span>•</span>
          {status}
          {s.counts_for_streak ? <span className="font-mono text-secondary">+{s.points_awarded} pts</span> : <span className="font-mono">extra (no pts)</span>}
        </p>
      </div>
      {(isArticle || s.ai_feedback) && <Icon name="chevron_right" className="text-on-surface-variant" />}
    </div>
  )
  return <li>{isArticle || s.ai_feedback ? <Link to={`/grading/${s.id}`}>{body}</Link> : body}</li>
}

function GraderInsight({ s }: { s: Submission }) {
  return (
    <section className="card flex flex-col gap-5 p-6 sm:flex-row sm:items-center">
      <ScoreRing value={s.ai_score ?? 0} size={96} stroke={8} color="#15803d" label={s.ai_score} sub="/ 10" />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 font-mono text-label-sm text-primary-container uppercase">
          <Icon name="psychology" className="text-[16px]" /> AI grader insights · Day {s.day_number}
        </p>
        <p className="mt-1 text-headline-md text-ink">“{submissionTitle(s)}”</p>
        {s.ai_feedback && <p className="mt-1 line-clamp-3 text-body-md text-on-surface-variant">{s.ai_feedback}</p>}
      </div>
      <Link to={`/grading/${s.id}`} className="btn shrink-0 bg-primary-fixed text-primary-container hover:bg-primary-fixed-dim">
        View full critique <Icon name="arrow_forward" className="text-[18px]" />
      </Link>
    </section>
  )
}

function TodayCard({ challenge, day, inWindow, submitted, timezone }: { challenge: Challenge; day: number; inWindow: boolean; submitted: boolean; timezone: string }) {
  const secs = useCountdown(timezone)
  const types = challenge.task_types_allowed === 'both' ? 'Code or article' : challenge.task_types_allowed === 'code' ? 'Code' : 'Article'
  return (
    <section className="rounded-2xl bg-primary-container p-6 text-white shadow-lift">
      <div className="flex items-center justify-between">
        {inWindow && !submitted ? (
          <span className="pill bg-white/15 font-bold text-white">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-secondary-fixed-dim" /> Due in {formatCountdown(secs)}
          </span>
        ) : (
          <span className="pill bg-white/15 font-bold text-white">{submitted ? '✓ Submitted' : inWindow ? '' : 'Closed'}</span>
        )}
        <span className="font-mono text-label-sm text-white/70">Today</span>
      </div>
      <p className="mt-5 font-mono text-label-sm tracking-wider text-white/70 uppercase">
        {challenge.name} · Day {Math.max(1, Math.min(day, challenge.total_days))}
      </p>
      <h3 className="mt-1 text-headline-lg">{submitted ? 'Task logged, streak safe' : inWindow ? `Day ${day} is open` : 'No open day right now'}</h3>
      <p className="mt-2 text-body-md text-white/80">
        {challenge.description ?? `${types} submissions count toward your streak.`}
      </p>
      {inWindow && (
        <Link to="/submit" className="btn mt-6 h-11 w-full bg-white text-primary-container hover:bg-primary-fixed">
          <Icon name={submitted ? 'add' : 'play_arrow'} filled className="text-[20px]" />
          {submitted ? 'Submit another' : 'Start Task Now'}
        </Link>
      )}
    </section>
  )
}

function WeekCard({ today, done, challenge }: { today: string; done: Map<string, SubmissionType>; challenge: Challenge }) {
  const weekday = (parseDay(today).getUTCDay() + 6) % 7
  const monday = addDays(today, -weekday)
  const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i))
  const inChallenge = days.filter((d) => d >= challenge.start_date && d <= challenge.end_date && d <= today)
  const count = days.filter((d) => done.has(d)).length
  const pct = inChallenge.length ? Math.round((count / inChallenge.length) * 100) : 0
  return (
    <section className="card p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="label">This week</p>
          <p className="mt-1 text-headline-md text-ink">
            {count} / {inChallenge.length || 7} days done
          </p>
        </div>
        <span className="pill bg-secondary-container font-bold text-on-secondary-container">{pct}%</span>
      </div>
      <div className="mt-5 grid grid-cols-7 gap-2 text-center">
        {days.map((d, i) => {
          const isDone = done.has(d)
          const isToday = d === today
          const future = d > today
          return (
            <div key={d} className="flex flex-col items-center gap-1.5">
              <span className={`font-mono text-label-sm ${isToday ? 'text-primary-container' : 'text-on-surface-variant'}`}>{'MTWTFSS'[i]}</span>
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-lg ${isDone ? 'bg-heat-4 text-white' : isToday ? 'bg-primary-fixed text-primary-container ring-2 ring-primary-container/30' : future ? 'bg-surface-container-low text-outline-variant' : 'bg-heat-0 text-outline'}`}
                title={d}
              >
                <Icon name={isDone ? 'check' : isToday ? 'schedule' : future ? 'more_horiz' : 'close'} className="text-[18px]" />
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function MilestoneCard({ streak, every, bonus }: { streak: number; every: number; bonus: number }) {
  const next = (Math.floor(streak / every) + 1) * every
  const progress = ((streak % every) / every) * 100
  return (
    <section className="card p-6">
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-tertiary-fixed text-tertiary">
          <Icon name="military_tech" filled />
        </span>
        <div>
          <p className="label">Next milestone</p>
          <p className="text-headline-md text-ink">{next}-day streak</p>
        </div>
      </div>
      <div className="mt-4 flex justify-between text-body-md">
        <span className="text-ink">
          {streak} / {next} days
        </span>
        <span className="font-mono text-label-md text-primary-container">{next - streak} to go</span>
      </div>
      <div className="mt-2">
        <ProgressBar value={progress} className="bg-tertiary-container" />
      </div>
      <p className="mt-4 flex items-center gap-2 rounded-lg bg-surface-container-low p-3 text-body-md text-on-surface-variant">
        <Icon name="redeem" className="text-streak" />
        <span>
          Reward: <b className="text-ink">+{bonus} bonus pts</b> every {every} days in a row
        </span>
      </p>
    </section>
  )
}
