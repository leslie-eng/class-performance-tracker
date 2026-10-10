import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ClassNotesForm } from '../components/ClassNotesForm'
import { Avatar, ErrorBanner, Icon } from '../components/ui'
import { api } from '../lib/api'
import { addDays } from '../lib/dates'
import { keys, useChallenges } from '../lib/queries'
import { useSession } from '../lib/session'
import type { Challenge, DropPreview, LaggingMember, TaskTypes, User } from '../lib/types'

interface NotificationRow {
  id: number
  user_id: number
  type: string
  message_sent: string
  status: string
  error: string | null
  sent_at: string
}

export default function AdminPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-headline-lg text-ink md:text-[28px]">Admin</h1>
        <p className="text-body-md text-on-surface-variant">Manage challenges, members, the Friday Drop and WhatsApp nudges.</p>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <CreateChallenge />
        <ChallengeList />
        <FridayDrop />
        <Nudges />
        <Members />
      </div>
    </div>
  )
}

function CreateChallenge() {
  const { meta } = useSession()
  const qc = useQueryClient()
  const today = meta?.today ?? new Date().toISOString().slice(0, 10)
  const [f, setF] = useState({
    name: '',
    description: '',
    start_date: today,
    end_date: addDays(today, 99),
    task_types_allowed: 'both' as TaskTypes,
    code_points: 10,
    article_points: 15,
    streak_bonus_points: 5,
    backfill_days: 1,
    lag_threshold: 2,
    ai_code_review: false,
  })
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }))

  const create = useMutation({
    mutationFn: () =>
      api<Challenge>('/challenges', {
        method: 'POST',
        json: {
          name: f.name.trim(),
          description: f.description.trim() || null,
          start_date: f.start_date,
          end_date: f.end_date,
          task_types_allowed: f.task_types_allowed,
          scoring_rules: {
            code_points: f.code_points,
            article_points: f.article_points,
            streak_bonus_points: f.streak_bonus_points,
            backfill_days: f.backfill_days,
            lag_threshold: f.lag_threshold,
            ai_code_review: f.ai_code_review,
          },
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.challenges })
      setF((s) => ({ ...s, name: '', description: '' }))
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    create.mutate()
  }

  const num = (k: 'code_points' | 'article_points' | 'streak_bonus_points' | 'backfill_days' | 'lag_threshold', label: string, min = 0) => (
    <label className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      <input className="input" type="number" min={min} value={f[k]} onChange={(e) => set(k, Number(e.target.value))} />
    </label>
  )

  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="add_circle" className="text-primary-container" /> New challenge
      </h2>
      <form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={submit}>
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="label">Name</span>
          <input className="input" required value={f.name} onChange={(e) => set('name', e.target.value)} placeholder="100 Days of Python" />
        </label>
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="label">Description</span>
          <input className="input" value={f.description} onChange={(e) => set('description', e.target.value)} placeholder="One problem or article a day" />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Start date</span>
          <input className="input" type="date" required value={f.start_date} onChange={(e) => set('start_date', e.target.value)} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">End date</span>
          <input className="input" type="date" required value={f.end_date} onChange={(e) => set('end_date', e.target.value)} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Task types</span>
          <select className="input" value={f.task_types_allowed} onChange={(e) => set('task_types_allowed', e.target.value as TaskTypes)}>
            <option value="both">Code + articles</option>
            <option value="code">Code only</option>
            <option value="article">Articles only</option>
          </select>
        </label>
        {num('code_points', 'Code points')}
        {num('article_points', 'Article points')}
        {num('streak_bonus_points', 'Weekly streak bonus')}
        {num('backfill_days', 'Late logging (days)')}
        {num('lag_threshold', 'Nudge after N missed days', 1)}
        <label className="flex items-center gap-2 text-body-md text-ink sm:col-span-2">
          <input type="checkbox" className="h-[18px] w-[18px] accent-[#22c55e]" checked={f.ai_code_review} onChange={(e) => set('ai_code_review', e.target.checked)} />
          AI review for code submissions (feedback only)
        </label>
        <div className="flex flex-col gap-3 sm:col-span-2">
          <ErrorBanner error={create.error} />
          {create.isSuccess && <p className="text-body-md text-secondary">Challenge created. Members can join it now.</p>}
          <button className="btn-primary self-end" disabled={create.isPending}>
            Create challenge
          </button>
        </div>
      </form>
    </section>
  )
}

function ChallengeList() {
  const challenges = useChallenges()
  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="flag" className="text-primary-container" /> Challenges
      </h2>
      <ul className="mt-4 divide-y divide-slate-100">
        {(challenges.data ?? []).map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="truncate font-medium text-ink">{c.name}</p>
              <p className="font-mono text-label-sm text-on-surface-variant">
                {c.start_date} → {c.end_date} · {c.total_days} days · {c.task_types_allowed}
              </p>
            </div>
            <span className="font-mono text-label-sm text-on-surface-variant">#{c.id}</span>
          </li>
        ))}
        {!challenges.data?.length && <li className="py-3 text-body-md text-on-surface-variant">No challenges yet.</li>}
      </ul>
    </section>
  )
}

function FridayDrop() {
  const qc = useQueryClient()
  const [preview, setPreview] = useState<DropPreview | null>(null)
  const [monthly, setMonthly] = useState<{ dry_run: boolean; quizzes: { kind: string; specialization: string | null; duration: number; status: string }[]; notified: number } | null>(null)
  const drop = useMutation({
    mutationFn: ({ dry, week }: { dry: boolean; week: 'current' | 'upcoming' }) =>
      api<DropPreview>(`/admin/weekly/drop/run?dry_run=${dry}&week=${week}`, { method: 'POST' }),
    onSuccess: (r) => {
      setPreview(r)
      qc.invalidateQueries({ queryKey: ['admin', 'notifications'] })
    },
  })
  const runMonthly = useMutation({
    mutationFn: (dry: boolean) => api<NonNullable<typeof monthly>>(`/admin/monthly/run?dry_run=${dry}`, { method: 'POST' }),
    onSuccess: setMonthly,
  })

  return (
    <section className="card p-6 xl:col-span-2">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="event_note" className="text-primary-container" /> Friday Drop
      </h2>
      <p className="mt-1 text-body-md text-on-surface-variant">
        Goes out every Friday morning: the class-notes summary, the two projects and the quizzes. Members can add notes too.
      </p>
      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <ClassNotesForm />
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" disabled={drop.isPending} onClick={() => drop.mutate({ dry: true, week: 'upcoming' })}>
              <Icon name="visibility" className="text-[18px]" /> Preview next drop
            </button>
            <button className="btn-ghost" disabled={drop.isPending} onClick={() => drop.mutate({ dry: true, week: 'current' })}>
              Preview this week's
            </button>
            <button className="btn-primary" disabled={drop.isPending} onClick={() => drop.mutate({ dry: false, week: 'current' })}>
              <Icon name="send" className="text-[18px]" /> Send this week's drop
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" disabled={runMonthly.isPending} onClick={() => runMonthly.mutate(true)}>
              Preview monthly quizzes
            </button>
            <button className="btn-ghost" disabled={runMonthly.isPending} onClick={() => runMonthly.mutate(false)}>
              Generate monthly quizzes now
            </button>
          </div>
          <ErrorBanner error={drop.error ?? runMonthly.error} />
          {(drop.isPending || runMonthly.isPending) && <p className="text-body-sm text-on-surface-variant">Working… generating quizzes can take a minute.</p>}
          {preview && (
            <div className="flex flex-col gap-2">
              <p className="label">
                {preview.dry_run ? 'Preview' : `Sent to ${preview.sent}`} · drop of {preview.week_key}
                {preview.notes_missing && ' · no notes yet'}
              </p>
              <pre className="rounded-lg bg-surface-container-low p-3 font-mono text-label-sm whitespace-pre-wrap break-words text-ink">{preview.message}</pre>
              <ul className="flex flex-col gap-1 text-body-sm">
                {preview.recipients.map((r) => (
                  <li key={r.user_id} className="flex justify-between gap-3">
                    <span className="truncate text-ink">{r.name}</span>
                    <span className="shrink-0 text-on-surface-variant">{r.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {monthly && (
            <div>
              <p className="label">{monthly.dry_run ? 'Monthly preview' : `Monthly quizzes · ${monthly.notified} notified`}</p>
              <ul className="mt-1 flex flex-col gap-1 text-body-sm">
                {monthly.quizzes.map((q) => (
                  <li key={`${q.kind}-${q.specialization}-${q.duration}`} className="flex justify-between gap-3">
                    <span className="text-ink">
                      {q.kind}
                      {q.specialization ? ` · ${q.specialization.replace(/_/g, ' ')}` : ''} · {q.duration} min
                    </span>
                    <span className="shrink-0 text-on-surface-variant">{q.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function Nudges() {
  const [lagging, setLagging] = useState<{ dry: boolean; rows: LaggingMember[] } | null>(null)
  const [digest, setDigest] = useState<string | null>(null)
  const log = useQuery({ queryKey: ['admin', 'notifications'], queryFn: () => api<NotificationRow[]>('/admin/notifications?limit=20') })

  const run = useMutation({
    mutationFn: (dry: boolean) => api<{ lagging: LaggingMember[] }>(`/admin/notify/run?dry_run=${dry}`, { method: 'POST' }),
    onSuccess: (r, dry) => {
      setLagging({ dry, rows: r.lagging })
      log.refetch()
    },
  })
  const runDigest = useMutation({
    mutationFn: () => api<{ message: string }>('/admin/digest/run?dry_run=true', { method: 'POST' }),
    onSuccess: (r) => setDigest(r.message),
  })

  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="notifications_active" className="text-primary-container" /> WhatsApp nudges
      </h2>
      <p className="mt-1 text-body-md text-on-surface-variant">
        The lag check runs every evening on its own. Preview it here, or send the nudges now.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn-secondary" onClick={() => run.mutate(true)} disabled={run.isPending}>
          <Icon name="visibility" className="text-[18px]" /> Preview lag check
        </button>
        <button className="btn-primary" onClick={() => run.mutate(false)} disabled={run.isPending}>
          <Icon name="send" className="text-[18px]" /> Send nudges now
        </button>
        <button className="btn-ghost" onClick={() => runDigest.mutate()} disabled={runDigest.isPending}>
          Preview weekly digest
        </button>
      </div>
      <div className="mt-3">
        <ErrorBanner error={run.error ?? runDigest.error} />
      </div>
      {lagging && (
        <div className="mt-4">
          <p className="label">{lagging.dry ? 'Preview' : 'Sent'}: {lagging.rows.length} lagging</p>
          <ul className="mt-2 flex flex-col gap-2">
            {lagging.rows.map((m) => (
              <li key={`${m.user_id}-${m.challenge_id}`} className="rounded-lg bg-surface-container-low p-3 text-body-md">
                <p className="font-medium text-ink">
                  {m.name} · {m.challenge} · {m.days_missed} days missed
                  {m.notified && <span className="ml-2 text-secondary">✓ nudged</span>}
                </p>
                {m.skipped_reason && <p className="mt-1 text-body-sm text-on-surface-variant">{m.skipped_reason}</p>}
              </li>
            ))}
            {!lagging.rows.length && <li className="text-body-md text-secondary">Everyone is on pace.</li>}
          </ul>
        </div>
      )}
      {digest && <pre className="mt-4 rounded-lg bg-surface-container-low p-3 font-mono text-label-sm whitespace-pre-wrap text-ink">{digest}</pre>}
      <p className="label mt-6">Recent notifications</p>
      <ul className="mt-2 divide-y divide-slate-100">
        {(log.data ?? []).map((n) => (
          <li key={n.id} className="py-2 text-body-sm">
            <span className={n.status === 'sent' ? 'text-secondary' : 'text-error'}>{n.status}</span> ·{' '}
            <span className="text-on-surface-variant">{new Date(n.sent_at).toLocaleString()}</span>
            <p className="truncate text-ink">{n.message_sent}</p>
          </li>
        ))}
        {!log.data?.length && <li className="py-2 text-body-sm text-on-surface-variant">Nothing sent yet.</li>}
      </ul>
    </section>
  )
}

function Members() {
  const { user: me } = useSession()
  const members = useQuery({ queryKey: ['admin', 'members'], queryFn: () => api<User[]>('/members') })
  const toggle = useMutation({
    mutationFn: (u: User) => api<User>(`/admin/members/${u.id}/role?is_admin=${!u.is_admin}`, { method: 'PATCH' }),
    onSuccess: () => members.refetch(),
  })
  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="group" className="text-primary-container" /> Members ({members.data?.length ?? 0})
      </h2>
      <ErrorBanner error={toggle.error} />
      <ul className="mt-4 divide-y divide-slate-100">
        {(members.data ?? []).map((u) => (
          <li key={u.id} className="flex items-center gap-3 py-3">
            <Avatar name={u.name} id={u.id} size={32} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-ink">{u.name}</p>
              <p className="truncate text-body-sm text-on-surface-variant">
                {u.email}
                {u.whatsapp_opt_in && ' · WhatsApp ✓'}
              </p>
            </div>
            <button
              className={`pill ${u.is_admin ? 'bg-primary-fixed text-primary-container' : 'bg-surface-container-low text-on-surface-variant'}`}
              disabled={u.id === me?.id || toggle.isPending}
              onClick={() => toggle.mutate(u)}
              title={u.id === me?.id ? "You can't change your own role" : 'Toggle admin'}
            >
              {u.is_admin ? 'admin' : 'member'}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
