import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../lib/api'
import type { AdminQuestion, AdminQuiz, AdminQuizDetail } from '../../lib/types'
import { ErrorBanner, Icon, Spinner } from '../ui'

const STATUS_CLS: Record<AdminQuiz['status'], string> = {
  published: 'bg-secondary-container text-on-secondary-container',
  draft: 'bg-primary-fixed text-primary-container',
  generating: 'bg-surface-container-high text-on-surface-variant',
  failed: 'bg-error-container text-on-error-container',
}

/** Admin quiz list and review: answer keys, inline edits, publish/unpublish. */
export function QuizReview() {
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const list = useQuery({
    queryKey: ['admin', 'quizzes', status],
    queryFn: () => api<AdminQuiz[]>(`/admin/quizzes${status ? `?status_filter=${status}` : ''}`),
  })
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <section className="card min-w-0 p-6">
        <div className="flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-headline-md text-ink">
            <Icon name="quiz" className="text-primary-container" /> Quizzes
          </h2>
          <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">All</option>
            <option value="draft">Drafts</option>
            <option value="published">Published</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <ErrorBanner error={list.error} />
        <ul className="mt-4 divide-y divide-slate-100">
          {(list.data ?? []).map((q) => (
            <li key={q.id}>
              <button className={`flex w-full items-start gap-3 py-3 text-left ${open === q.id ? 'font-semibold' : ''}`} onClick={() => setOpen(q.id)}>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-ink">
                    {q.kind} · {q.period_key}
                    {q.specialization ? ` · ${q.specialization.replace(/_/g, ' ')}` : ''} · {q.duration_minutes} min
                  </span>
                  <span className="block text-body-sm font-normal text-on-surface-variant">
                    {q.question_count} questions · {q.attempts} attempts · {q.sources.length ? `${q.sources.length} materials` : 'notes/summaries only'}
                  </span>
                </span>
                <span className={`pill shrink-0 ${STATUS_CLS[q.status]}`}>{q.status}</span>
              </button>
            </li>
          ))}
          {list.data && !list.data.length && <li className="py-3 text-body-md text-on-surface-variant">No quizzes yet.</li>}
        </ul>
      </section>
      {open ? <QuizEditor key={open} id={open} /> : <p className="text-body-md text-on-surface-variant">Pick a quiz to review it.</p>}
    </div>
  )
}

function QuizEditor({ id }: { id: number }) {
  const qc = useQueryClient()
  const quiz = useQuery({ queryKey: ['admin', 'quiz', id], queryFn: () => api<AdminQuizDetail>(`/admin/quizzes/${id}`) })
  const [draft, setDraft] = useState<AdminQuestion[] | null>(null)
  const done = (q: AdminQuizDetail) => {
    qc.setQueryData(['admin', 'quiz', id], q)
    qc.invalidateQueries({ queryKey: ['admin', 'quizzes'] })
    setDraft(null)
  }
  const save = useMutation({
    mutationFn: (questions: AdminQuestion[]) => api<AdminQuizDetail>(`/admin/quizzes/${id}`, { method: 'PATCH', json: { questions } }),
    onSuccess: done,
  })
  const setStatus = useMutation({
    mutationFn: (status: 'draft' | 'published') =>
      status === 'published'
        ? api<AdminQuizDetail>(`/admin/quizzes/${id}/publish`, { method: 'POST' })
        : api<AdminQuizDetail>(`/admin/quizzes/${id}`, { method: 'PATCH', json: { status } }),
    onSuccess: done,
  })

  if (quiz.isLoading) return <Spinner />
  if (!quiz.data) return <ErrorBanner error={quiz.error} />
  const q = quiz.data
  const questions = draft ?? q.questions
  const edit = (i: number, patch: Partial<AdminQuestion>) => setDraft(questions.map((x, j) => (j === i ? { ...x, ...patch } : x)))

  return (
    <section className="card min-w-0 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-headline-md text-ink">
          {q.kind} · {q.duration_minutes} min <span className={`pill ml-2 align-middle ${STATUS_CLS[q.status]}`}>{q.status}</span>
        </h2>
        <div className="flex gap-2">
          {q.status === 'published' ? (
            <button className="btn-secondary" disabled={setStatus.isPending} onClick={() => setStatus.mutate('draft')}>
              Unpublish
            </button>
          ) : (
            <button className="btn-primary" disabled={setStatus.isPending || !q.questions.length || !!draft} onClick={() => setStatus.mutate('published')}>
              Publish
            </button>
          )}
        </div>
      </div>
      {q.error && <p className="mt-2 text-body-sm text-error">{q.error}</p>}
      <p className="mt-2 text-body-sm text-on-surface-variant">
        Generated from: {q.sources.length ? q.sources.map((s) => s.title).join(', ') : 'class notes and weekly summaries'}
      </p>
      <ErrorBanner error={save.error ?? setStatus.error} />
      <ol className="mt-4 flex flex-col gap-4">
        {questions.map((x, i) => (
          <li key={x.id} className="rounded-xl border border-slate-100 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="label">
                {i + 1}. {x.type === 'mcq' ? 'Multiple choice' : 'Short answer'}
              </span>
              <label className="ml-auto flex items-center gap-1 text-body-sm text-on-surface-variant">
                Difficulty
                <select className="input h-8 w-16 px-2" value={x.difficulty} onChange={(e) => edit(i, { difficulty: Number(e.target.value) })}>
                  {[1, 2, 3, 4, 5].map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-1 text-body-sm text-on-surface-variant">
                Points
                <input className="input h-8 w-16 px-2" type="number" min={1} max={20} value={x.points} onChange={(e) => edit(i, { points: Number(e.target.value) })} />
              </label>
              <button className="btn-ghost h-8 px-2" onClick={() => setDraft(questions.filter((_, j) => j !== i))} aria-label={`Delete question ${i + 1}`}>
                <Icon name="delete" className="text-[18px]" />
              </button>
            </div>
            <textarea className="input mt-2 h-auto min-h-16 py-2" value={x.prompt} onChange={(e) => edit(i, { prompt: e.target.value })} />
            {x.type === 'mcq' ? (
              <div className="mt-2 flex flex-col gap-1.5">
                {(x.options ?? []).map((opt, k) => (
                  <label key={k} className="flex items-center gap-2">
                    <input type="radio" name={`${x.id}-key`} className="accent-[#15803d]" checked={x.answer_key === k} onChange={() => edit(i, { answer_key: k })} aria-label="Correct option" />
                    <input
                      className="input h-9"
                      value={opt}
                      onChange={(e) => edit(i, { options: (x.options ?? []).map((o, n) => (n === k ? e.target.value : o)) })}
                    />
                  </label>
                ))}
              </div>
            ) : (
              <label className="mt-2 flex flex-col gap-1">
                <span className="label">Model answer</span>
                <textarea className="input h-auto min-h-12 py-2" value={String(x.answer_key)} onChange={(e) => edit(i, { answer_key: e.target.value })} />
              </label>
            )}
            <label className="mt-2 flex flex-col gap-1">
              <span className="label">Explanation</span>
              <input className="input" value={x.explanation} onChange={(e) => edit(i, { explanation: e.target.value })} />
            </label>
          </li>
        ))}
      </ol>
      {draft && (
        <div className="sticky bottom-2 mt-4 flex justify-end gap-2 rounded-xl bg-white/90 p-2 backdrop-blur">
          <button className="btn-ghost" onClick={() => setDraft(null)}>
            Discard changes
          </button>
          <button className="btn-primary" disabled={save.isPending || !draft.length} onClick={() => save.mutate(draft)}>
            Save questions
          </button>
        </div>
      )}
    </section>
  )
}
