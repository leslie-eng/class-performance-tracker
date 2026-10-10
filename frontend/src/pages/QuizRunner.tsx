import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ErrorBanner, Icon, PageLoader, ProgressBar, ScoreRing } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { formatCountdown } from '../lib/dates'
import { keys, useQuizAttempt } from '../lib/queries'
import type { QuizAnswers, QuizAttempt, QuizKind, QuizQuestion, QuizResult } from '../lib/types'
import { useDeadline } from '../lib/useDeadline'

const TITLE: Record<QuizKind, string> = { weekly: 'Weekly quiz', course: 'Course review', interview: 'Interview prep' }

export default function QuizRunnerPage() {
  const { attemptId } = useParams()
  const attempt = useQuizAttempt(Number(attemptId))
  if (attempt.isLoading) return <PageLoader />
  if (attempt.error || !attempt.data) return <ErrorBanner error={attempt.error ?? 'Quiz not found'} />
  return attempt.data.submitted ? <Results a={attempt.data} /> : <Runner key={attempt.data.id} a={attempt.data} />
}

function difficultyLabel(d: number) {
  return d <= 2 ? 'Easy' : d === 3 ? 'Medium' : 'Hard'
}

function DifficultyMeter({ level }: { level: number }) {
  return (
    <span className="flex items-center gap-2" aria-label={`Difficulty ${level} of 5`}>
      <span className="flex items-end gap-0.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <span
            key={n}
            className={`w-1.5 rounded-sm ${n <= level ? (level >= 4 ? 'bg-tertiary-container' : 'bg-primary-container') : 'bg-surface-container-high'}`}
            style={{ height: 4 + n * 3 }}
          />
        ))}
      </span>
      <span className="font-mono text-label-sm text-on-surface-variant">{difficultyLabel(level)}</span>
    </span>
  )
}

function Runner({ a }: { a: QuizAttempt }) {
  const qc = useQueryClient()
  const [answers, setAnswers] = useState<QuizAnswers>(a.answers)
  const [index, setIndex] = useState(() => {
    const firstOpen = a.questions.findIndex((q) => !(q.id in a.answers))
    return firstOpen === -1 ? a.questions.length - 1 : firstOpen
  })
  const [confirming, setConfirming] = useState(false)
  const timers = useRef<Record<string, number>>({})
  const autoSubmitted = useRef(false)
  const secs = useDeadline(a.ends_at, a.server_now)

  const refetch = (err: unknown) => {
    // 409: time ran out or it was submitted elsewhere; the server graded it, so show that.
    if (err instanceof ApiError && err.status === 409) qc.invalidateQueries({ queryKey: keys.attempt(a.id) })
  }
  const save = useMutation({
    mutationFn: (patch: QuizAnswers) =>
      api<QuizAttempt>(`/quizzes/attempts/${a.id}/answers`, { method: 'PATCH', json: { answers: patch } }),
    onError: refetch,
  })
  const submit = useMutation({
    mutationFn: () => api<QuizAttempt>(`/quizzes/attempts/${a.id}/submit`, { method: 'POST', json: { answers } }),
    onSuccess: (r) => {
      qc.setQueryData(keys.attempt(a.id), r)
      qc.invalidateQueries({ queryKey: keys.weekly })
      qc.invalidateQueries({ queryKey: keys.quizLeaderboard })
    },
    onError: refetch,
  })

  useEffect(() => {
    if (secs === 0 && !autoSubmitted.current) {
      autoSubmitted.current = true
      submit.mutate()
    }
  }, [secs, submit])

  function answer(qid: string, value: number | string, debounce = false) {
    setAnswers((prev) => ({ ...prev, [qid]: value }))
    window.clearTimeout(timers.current[qid])
    if (debounce) timers.current[qid] = window.setTimeout(() => save.mutate({ [qid]: value }), 800)
    else save.mutate({ [qid]: value })
  }

  const q = a.questions[index]
  const answered = a.questions.filter((x) => x.id in answers && String(answers[x.id]).trim() !== '').length
  const last = index === a.questions.length - 1
  const lowTime = secs <= 60

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="card sticky top-2 z-10 flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="label">{TITLE[a.kind]} · {a.duration_minutes} min</p>
            <p className="text-body-sm text-on-surface-variant">
              {answered}/{a.questions.length} answered ·{' '}
              {save.isPending ? 'Saving…' : save.isError ? 'Not saved, retrying on next answer' : 'All answers saved'}
            </p>
          </div>
          <span
            className={`font-mono text-headline-md tabular-nums ${lowTime ? 'text-error' : 'text-ink'}`}
            role="timer"
            aria-live={lowTime ? 'polite' : 'off'}
          >
            {formatCountdown(secs)}
          </span>
        </div>
        <ProgressBar value={(answered / a.questions.length) * 100} />
      </div>

      <section className="card p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="label">
            Question {index + 1} of {a.questions.length} · {q.points} pt{q.points === 1 ? '' : 's'}
          </p>
          <DifficultyMeter level={q.difficulty} />
        </div>
        <p className="mt-3 text-body-lg break-words whitespace-pre-wrap text-ink">{q.prompt}</p>
        <QuestionInput q={q} value={answers[q.id]} onAnswer={answer} />
      </section>

      <ErrorBanner error={submit.error ?? (save.error instanceof ApiError && save.error.status === 409 ? null : save.error)} />

      <div className="flex items-center justify-between gap-2">
        <button className="btn-secondary" disabled={index === 0} onClick={() => setIndex((i) => i - 1)}>
          <Icon name="arrow_back" className="text-[18px]" /> Previous
        </button>
        {!last ? (
          <button className="btn-primary" onClick={() => setIndex((i) => i + 1)}>
            Next <Icon name="arrow_forward" className="text-[18px]" />
          </button>
        ) : confirming ? (
          <span className="flex gap-2">
            <button className="btn-ghost" onClick={() => setConfirming(false)}>
              Keep working
            </button>
            <button className="btn-primary" disabled={submit.isPending} onClick={() => submit.mutate()}>
              {submit.isPending ? 'Grading…' : 'Submit now'}
            </button>
          </span>
        ) : (
          <button className="btn-primary" onClick={() => setConfirming(true)}>
            Submit quiz
          </button>
        )}
      </div>

      <nav className="flex flex-wrap gap-1.5" aria-label="Questions">
        {a.questions.map((x, i) => (
          <button
            key={x.id}
            onClick={() => setIndex(i)}
            aria-current={i === index}
            className={`h-8 w-8 rounded-lg font-mono text-label-sm ${
              i === index
                ? 'bg-primary-container text-white'
                : x.id in answers
                  ? 'bg-secondary-container text-on-secondary-container'
                  : 'bg-surface-container-low text-on-surface-variant'
            }`}
          >
            {i + 1}
          </button>
        ))}
      </nav>
      {submit.isPending && <p className="text-center text-body-sm text-on-surface-variant">Grading your answers…</p>}
    </div>
  )
}

function QuestionInput({
  q,
  value,
  onAnswer,
}: {
  q: QuizQuestion
  value: number | string | undefined
  onAnswer: (qid: string, value: number | string, debounce?: boolean) => void
}) {
  if (q.type === 'mcq')
    return (
      <fieldset className="mt-4 flex flex-col gap-2">
        <legend className="sr-only">Choose one answer</legend>
        {(q.options ?? []).map((opt, i) => (
          <label
            key={i}
            className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-body-md ${
              value === i ? 'border-primary-container bg-primary-fixed/40' : 'border-slate-200 hover:bg-slate-50'
            }`}
          >
            <input type="radio" name={q.id} className="mt-1 accent-[#2563eb]" checked={value === i} onChange={() => onAnswer(q.id, i)} />
            <span className="break-words text-ink">{opt}</span>
          </label>
        ))}
      </fieldset>
    )
  return (
    <label className="mt-4 flex flex-col gap-1.5">
      <span className="label">Your answer (1-3 sentences)</span>
      <textarea
        className="input h-auto min-h-32 py-2"
        maxLength={2000}
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => onAnswer(q.id, e.target.value, true)}
      />
    </label>
  )
}

function answerText(r: QuizResult, value: number | string | null) {
  if (value === null || value === undefined || value === '') return '—'
  return r.type === 'mcq' && typeof value === 'number' ? (r.options?.[value] ?? '—') : String(value)
}

function Results({ a }: { a: QuizAttempt }) {
  const score = a.score ?? 0
  const pct = a.max_score ? score / a.max_score : 0
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <section className="card flex flex-col items-center gap-3 p-6 text-center">
        <p className="label">{TITLE[a.kind]} · {a.duration_minutes} min</p>
        <ScoreRing value={score} max={a.max_score || 1} label={score} sub={`/ ${a.max_score}`} color={pct >= 0.7 ? '#15803d' : pct >= 0.4 ? '#2563eb' : '#d97706'} />
        <p className="text-body-md text-on-surface-variant">{a.points_awarded} quiz points earned</p>
        {a.late && (
          <p className="rounded-lg bg-tertiary-fixed px-3 py-2 text-body-sm text-tertiary">
            Time ran out before your submit arrived, so your last saved answers were graded.
          </p>
        )}
        {a.grading_status === 'failed' && (
          <p className="rounded-lg bg-error-container px-3 py-2 text-body-sm text-on-error-container">
            Short answers couldn't be graded automatically yet{a.grading_error ? ` (${a.grading_error})` : ''}. Multiple-choice points are counted.
          </p>
        )}
        <Link to="/weekly" className="btn-secondary">
          Back to this week
        </Link>
      </section>
      <ol className="flex flex-col gap-3">
        {(a.results ?? []).map((r, i) => {
          const full = r.earned >= r.points
          return (
            <li key={r.id} className="card p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="label">
                  {i + 1}. {difficultyLabel(r.difficulty)}
                </p>
                <span className={`pill ${full ? 'bg-secondary-container text-on-secondary-container' : r.earned > 0 ? 'bg-primary-fixed text-primary-container' : 'bg-error-container text-on-error-container'}`}>
                  {r.earned}/{r.points}
                </span>
              </div>
              <p className="mt-2 break-words whitespace-pre-wrap text-ink">{r.prompt}</p>
              <dl className="mt-3 grid gap-1 text-body-md">
                <div className="flex gap-2">
                  <dt className="shrink-0 text-on-surface-variant">Your answer:</dt>
                  <dd className="min-w-0 break-words text-ink">{answerText(r, r.your_answer)}</dd>
                </div>
                {!full && (
                  <div className="flex gap-2">
                    <dt className="shrink-0 text-on-surface-variant">{r.type === 'mcq' ? 'Correct:' : 'Model answer:'}</dt>
                    <dd className="min-w-0 break-words text-ink">{answerText(r, r.correct_answer)}</dd>
                  </div>
                )}
              </dl>
              {r.feedback && <p className="mt-2 text-body-md text-ink">{r.feedback}</p>}
              <p className="mt-2 text-body-sm text-on-surface-variant">{r.explanation}</p>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
