import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ClassNotesForm } from '../components/ClassNotesForm'
import { EmptyState, ErrorBanner, Icon, Modal, PageLoader } from '../components/ui'
import { api } from '../lib/api'
import { shortDate } from '../lib/dates'
import { keys, useQuizLeaderboard, useWeekly } from '../lib/queries'
import { useSession } from '../lib/session'
import type { Proposal, QuizAttempt, QuizKind, QuizSlot, WeeklyCurrent } from '../lib/types'

const KIND_LABEL: Record<QuizKind, string> = {
  weekly: "This week's quiz",
  course: 'Course review (monthly)',
  interview: 'Interview prep (monthly)',
}

const specLabel = (s: string | null) => (s ?? 'general').replace(/_/g, ' ')

export default function WeeklyPage() {
  const weekly = useWeekly()
  if (weekly.isLoading) return <PageLoader />
  if (weekly.error || !weekly.data) return <ErrorBanner error={weekly.error ?? 'Could not load this week'} />
  const w = weekly.data
  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="label">Friday Drop · {shortDate(w.week_key)}</p>
        <h1 className="text-headline-lg text-ink md:text-[28px]">This week in class</h1>
      </header>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          <Summary w={w} />
          <Quizzes w={w} />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          <Projects w={w} />
          <NextWeek w={w} />
          <QuizBoard />
        </div>
      </div>
    </div>
  )
}

function Summary({ w }: { w: WeeklyCurrent }) {
  const b = w.brief
  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="auto_stories" className="text-primary-container" /> Core concepts
      </h2>
      {b?.summary ? (
        <>
          <p className="mt-3 text-body-lg whitespace-pre-line text-ink">{b.summary}</p>
          {b.concepts.length > 0 && (
            <ul className="mt-5 grid gap-3 sm:grid-cols-2">
              {b.concepts.map((c) => (
                <li key={c.title} className="rounded-xl bg-surface-container-low p-4">
                  <p className="font-semibold text-ink">{c.title}</p>
                  <p className="mt-1 text-body-md text-on-surface-variant">{c.one_liner}</p>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <EmptyState icon="hourglass_empty" title="The summary isn't ready yet">
          {!b?.has_notes
            ? 'No class notes were added for this week. Anyone in the group can add notes for next Friday below.'
            : !w.ai_configured
              ? "AI summaries aren't configured on this server yet."
              : (b?.summary_error ?? 'It is being written; check back in a minute.')}
        </EmptyState>
      )}
    </section>
  )
}

function Quizzes({ w }: { w: WeeklyCurrent }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const start = useMutation({
    mutationFn: (s: QuizSlot) => api<QuizAttempt>(`/quizzes/${s.kind}/start?duration=${s.duration_minutes}`, { method: 'POST' }),
    onSuccess: (attempt) => {
      qc.setQueryData(keys.attempt(attempt.id), attempt)
      qc.invalidateQueries({ queryKey: keys.weekly })
      navigate(`/quiz/${attempt.id}`)
    },
  })
  const groups = (['weekly', 'course', 'interview'] as QuizKind[]).map((kind) => ({
    kind,
    slots: w.quizzes.filter((s) => s.kind === kind),
  }))

  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="timer" className="text-primary-container" /> Quizzes
      </h2>
      <p className="mt-1 text-body-md text-on-surface-variant">
        Pick a length. Questions start easy and get harder. You get one attempt per quiz, and your answers save as you go.
      </p>
      <div className="mt-3">
        <ErrorBanner error={start.error} />
      </div>
      <div className="mt-4 flex flex-col gap-5">
        {groups.map(({ kind, slots }) => (
          <div key={kind}>
            <p className="label">
              {KIND_LABEL[kind]}
              {kind === 'interview' && slots[0] && ` · ${specLabel(slots[0].specialization)}`}
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              {slots.map((s) => (
                <QuizButton key={s.duration_minutes} slot={s} busy={start.isPending} onStart={() => start.mutate(s)} />
              ))}
            </div>
            {slots.every((s) => !s.available && !s.attempt_id) && slots[0]?.reason && (
              <p className="mt-2 text-body-sm text-on-surface-variant">{slots[0].reason}</p>
            )}
          </div>
        ))}
      </div>
      {start.isPending && <p className="mt-3 text-body-sm text-on-surface-variant">Preparing your quiz… the first start can take up to a minute.</p>}
    </section>
  )
}

function QuizButton({ slot, busy, onStart }: { slot: QuizSlot; busy: boolean; onStart: () => void }) {
  const label = (
    <>
      <span className="font-semibold">{slot.duration_minutes} min</span>
      <span className="text-body-sm opacity-80">{slot.question_count} questions</span>
    </>
  )
  const cls = 'flex h-auto flex-col items-start gap-0.5 rounded-xl px-4 py-3 text-left'
  if (slot.submitted && slot.attempt_id)
    return (
      <Link to={`/quiz/${slot.attempt_id}`} className={`btn-secondary ${cls}`}>
        {label}
        <span className="flex items-center gap-1 text-body-sm text-secondary">
          <Icon name="check_circle" className="text-[16px]" /> {slot.score ?? 0}/{slot.max_score} · results
        </span>
      </Link>
    )
  if (slot.attempt_id)
    return (
      <Link to={`/quiz/${slot.attempt_id}`} className={`btn-primary ${cls}`}>
        {label}
        <span className="text-body-sm">Resume</span>
      </Link>
    )
  return (
    <button className={`btn-secondary ${cls}`} disabled={!slot.available || busy} onClick={onStart} title={slot.reason ?? undefined}>
      {label}
      <span className="text-body-sm text-primary-container">{slot.available ? 'Start' : 'Not available'}</span>
    </button>
  )
}

function Projects({ w }: { w: WeeklyCurrent }) {
  const qc = useQueryClient()
  const pick = useMutation({
    mutationFn: (id: number) => api('/weekly/projects/pick', { method: 'PUT', json: { proposal_id: id } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.weekly }),
  })
  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="construction" className="text-primary-container" /> This week's projects
      </h2>
      <p className="mt-1 text-body-md text-on-surface-variant">Proposed by the group. Pick one; you can switch until next Friday.</p>
      <ErrorBanner error={pick.error} />
      {w.projects.length ? (
        <ul className="mt-4 flex flex-col gap-3">
          {w.projects.map((p) => (
            <ProjectCard key={p.id} p={p}>
              <button
                className={p.picked_by_me ? 'btn-primary' : 'btn-secondary'}
                disabled={p.picked_by_me || pick.isPending}
                onClick={() => pick.mutate(p.id)}
              >
                {p.picked_by_me ? (
                  <>
                    <Icon name="check" className="text-[18px]" /> Your pick
                  </>
                ) : (
                  'Pick this'
                )}
              </button>
              <span className="text-body-sm text-on-surface-variant">
                {p.picks} {p.picks === 1 ? 'member' : 'members'}
              </span>
            </ProjectCard>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-body-md text-on-surface-variant">No projects were proposed for this week.</p>
      )}
    </section>
  )
}

function ProjectCard({ p, children }: { p: Proposal; children?: ReactNode }) {
  return (
    <li className="rounded-xl border border-slate-100 p-4">
      <p className="font-semibold break-words text-ink">{p.title}</p>
      <p className="mt-1 text-body-md break-words whitespace-pre-line text-on-surface-variant">{p.description}</p>
      <p className="mt-2 text-body-sm text-on-surface-variant">Proposed by {p.proposer_name}</p>
      {children && <div className="mt-3 flex items-center gap-3">{children}</div>}
    </li>
  )
}

function NextWeek({ w }: { w: WeeklyCurrent }) {
  const { user } = useSession()
  const qc = useQueryClient()
  const [proposing, setProposing] = useState(false)
  const [notesOpen, setNotesOpen] = useState(false)
  const up = w.upcoming
  const withdraw = useMutation({
    mutationFn: (id: number) => api(`/weekly/projects/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.weekly }),
  })
  const blocked = up.my_proposal_id
    ? "You've proposed a project for next week."
    : up.slots_left === 0
      ? 'Both project slots for next week are taken.'
      : null

  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="event_upcoming" className="text-primary-container" /> Next drop · {shortDate(up.week_key)}
      </h2>
      <p className="label mt-4">Proposed projects ({up.projects.length}/2)</p>
      <ul className="mt-2 flex flex-col gap-3">
        {up.projects.map((p) => (
          <ProjectCard key={p.id} p={p}>
            {(p.proposer_id === user?.id || user?.is_admin) && (
              <button className="btn-ghost" disabled={withdraw.isPending} onClick={() => withdraw.mutate(p.id)}>
                Withdraw
              </button>
            )}
          </ProjectCard>
        ))}
      </ul>
      <ErrorBanner error={withdraw.error} />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button className="btn-primary" disabled={!!blocked} onClick={() => setProposing(true)}>
          <Icon name="add" className="text-[18px]" /> Propose a project
        </button>
        {blocked && <span className="text-body-sm text-on-surface-variant">{blocked}</span>}
      </div>
      <div className="mt-6 border-t border-slate-100 pt-4">
        <button className="flex w-full items-center justify-between text-left font-semibold text-ink" onClick={() => setNotesOpen((o) => !o)}>
          <span className="flex items-center gap-2">
            <Icon name="edit_note" className="text-primary-container" /> Class notes {up.has_notes ? '(added)' : '(missing)'}
          </span>
          <Icon name={notesOpen ? 'expand_less' : 'expand_more'} />
        </button>
        {!notesOpen && !up.has_notes && (
          <p className="mt-1 text-body-sm text-on-surface-variant">Without notes there's no summary or weekly quiz. Add them by Thursday night.</p>
        )}
        {notesOpen && (
          <div className="mt-3">
            <ClassNotesForm />
          </div>
        )}
      </div>
      {proposing && <ProposeModal onClose={() => setProposing(false)} />}
    </section>
  )
}

function ProposeModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const save = useMutation({
    mutationFn: () => api<Proposal>('/weekly/projects', { method: 'POST', json: { title: title.trim(), description: description.trim() } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.weekly })
      onClose()
    },
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    save.mutate()
  }
  return (
    <Modal title="Propose a project" onClose={onClose}>
      <form className="flex flex-col gap-4" onSubmit={submit}>
        <label className="flex flex-col gap-1.5">
          <span className="label">Title</span>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} minLength={3} maxLength={200} required />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">What would we build?</span>
          <textarea
            className="input h-auto min-h-28 py-2"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            minLength={10}
            maxLength={2000}
            required
          />
        </label>
        <p className="text-body-sm text-on-surface-variant">The first two proposals make it into next Friday's drop.</p>
        <ErrorBanner error={save.error} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={save.isPending}>
            Propose
          </button>
        </div>
      </form>
    </Modal>
  )
}

function QuizBoard() {
  const board = useQuizLeaderboard()
  const { user } = useSession()
  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="military_tech" className="text-primary-container" /> Quiz points
      </h2>
      <p className="mt-1 text-body-sm text-on-surface-variant">Separate from the challenge leaderboard and streaks.</p>
      <ul className="mt-3 divide-y divide-slate-100">
        {(board.data ?? []).slice(0, 10).map((r) => (
          <li key={r.user_id} className={`flex items-center gap-3 py-2 text-body-md ${r.user_id === user?.id ? 'font-semibold' : ''}`}>
            <span className="w-6 font-mono text-on-surface-variant">{r.rank}</span>
            <span className="min-w-0 flex-1 truncate text-ink">{r.name}</span>
            <span className="font-mono text-ink">{r.points}</span>
          </li>
        ))}
        {!board.data?.length && <li className="py-2 text-body-sm text-on-surface-variant">No quizzes taken yet.</li>}
      </ul>
    </section>
  )
}
