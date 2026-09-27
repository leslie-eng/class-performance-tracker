import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { EmptyState, ErrorBanner, Icon, PageLoader, ProgressBar, ScoreRing } from '../components/ui'
import { api } from '../lib/api'
import { relativeTime } from '../lib/dates'
import { useInvalidateProgress, useMySubmissions, useSubmission } from '../lib/queries'
import { articleHost, submissionTitle } from '../lib/submissions'
import type { RubricBreakdown, Submission } from '../lib/types'

const RUBRIC: { key: keyof RubricBreakdown; name: string; max: number; icon: string; tint: string; bar: string; desc: string }[] = [
  { key: 'clarity', name: 'Clarity & Structure', max: 3, icon: 'menu_book', tint: 'bg-secondary-container text-secondary', bar: 'bg-secondary', desc: 'Easy to follow for someone learning the topic' },
  { key: 'technical_accuracy', name: 'Technical Accuracy', max: 3, icon: 'code', tint: 'bg-primary-fixed text-primary-container', bar: 'bg-primary-container', desc: 'Claims and code examples are correct' },
  { key: 'depth', name: 'Depth of Analysis', max: 2, icon: 'insights', tint: 'bg-primary-fixed text-primary-container', bar: 'bg-primary-container', desc: 'Goes beyond a surface-level recap' },
  { key: 'originality', name: 'Originality & Insights', max: 2, icon: 'lightbulb', tint: 'bg-tertiary-fixed text-tertiary', bar: 'bg-tertiary-container', desc: 'Own examples and insights, not rehashed docs' },
]

function verdict(score: number) {
  if (score >= 8) return { label: 'Excellent work', cls: 'bg-secondary-container text-on-secondary-container', color: '#15803d' }
  if (score >= 6) return { label: 'Solid article', cls: 'bg-primary-fixed text-primary-container', color: '#2563eb' }
  return { label: 'Room to grow', cls: 'bg-tertiary-fixed text-tertiary', color: '#d97706' }
}

export default function GradingPage() {
  const { id } = useParams()
  const history = useMySubmissions()
  const reviewed = (history.data ?? []).filter((s) => s.submission_type === 'article' || s.grading_status !== 'not_applicable')

  if (!id) {
    if (history.isLoading) return <PageLoader />
    if (reviewed[0]) return <Navigate to={`/grading/${reviewed[0].id}`} replace />
    return (
      <div className="card mx-auto max-w-xl">
        <EmptyState icon="smart_toy" title="Nothing graded yet">
          Submit an article and the AI grader will score it on clarity, accuracy, depth and originality.
          <div className="mt-4">
            <Link to="/submit" className="btn-primary">
              Submit an article
            </Link>
          </div>
        </EmptyState>
      </div>
    )
  }
  return <GradingDetail id={Number(id)} history={reviewed} />
}

function GradingDetail({ id, history }: { id: number; history: Submission[] }) {
  const { data: s, isLoading, error } = useSubmission(id)
  const invalidate = useInvalidateProgress()
  const regrade = useMutation({
    mutationFn: () => api<Submission>(`/submissions/${id}/regrade`, { method: 'POST' }),
    onSuccess: invalidate,
  })

  if (isLoading) return <PageLoader />
  if (error || !s) return <ErrorBanner error={error ?? 'Submission not found'} />

  const isArticle = s.submission_type === 'article'
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <nav className="mb-1 font-mono text-label-sm text-on-surface-variant">
            AI Review › Day {s.day_number} Submission › <span className="text-ink">{isArticle ? 'Grade Critique' : 'Code Review'}</span>
          </nav>
          <h1 className="text-headline-lg text-ink md:text-[28px]">AI Evaluation & Technical Feedback</h1>
          <p className="mt-1 text-body-md text-on-surface-variant">Evaluated {isArticle ? 'article' : 'code'}:</p>
          {isArticle ? (
            <a href={s.content} target="_blank" rel="noreferrer" className="mt-1 inline-flex max-w-full items-center gap-1 truncate rounded-lg bg-primary-fixed/60 px-3 py-1 text-ink hover:bg-primary-fixed">
              “{submissionTitle(s)}” <Icon name="open_in_new" className="text-[16px]" />
            </a>
          ) : (
            <span className="mt-1 inline-block rounded-lg bg-primary-fixed/60 px-3 py-1 font-mono text-label-md text-ink">{s.language} · day {s.day_number}</span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="pill bg-surface-container-low text-on-surface-variant">
            <Icon name="schedule" className="text-[14px]" /> Submitted {relativeTime(s.submitted_at)}
          </span>
          {isArticle && (
            <span className="pill bg-surface-container-low text-on-surface-variant">
              <Icon name="public" className="text-[14px]" /> {articleHost(s.content)}
            </span>
          )}
          {s.grade_overridden && (
            <span className="pill bg-tertiary-fixed text-tertiary">
              <Icon name="verified_user" className="text-[14px]" /> Grade set by admin
            </span>
          )}
        </div>
      </div>

      {s.grading_status === 'pending' && <PendingState />}
      {s.grading_status === 'failed' && (
        <section className="card flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-error-container text-error">
              <Icon name="error" />
            </span>
            <div>
              <p className="font-semibold text-ink">Grading didn't complete</p>
              <p className="text-body-md text-on-surface-variant">{s.ai_feedback ?? 'Something went wrong while grading.'}</p>
              <p className="mt-1 text-body-sm text-on-surface-variant">
                {s.counts_for_streak ? `You still earned ${s.points_awarded} pts for this submission.` : 'This was an extra submission for the day, so it earns no points either way.'}
              </p>
            </div>
          </div>
          <button className="btn-primary shrink-0" onClick={() => regrade.mutate()} disabled={regrade.isPending}>
            <Icon name="refresh" className="text-[20px]" /> Retry grading
          </button>
        </section>
      )}
      <ErrorBanner error={regrade.error} />

      {s.grading_status === 'done' && isArticle && s.ai_score !== null && <ArticleResult s={s} />}
      {s.grading_status === 'done' && !isArticle && <CodeResult s={s} />}
      {s.grading_status === 'not_applicable' && (
        <div className="card">
          <EmptyState icon="code_off" title="No AI review for this submission">
            AI review for code is turned off for this challenge. Articles are always graded.
          </EmptyState>
        </div>
      )}

      <section className="card flex flex-col gap-3 p-5 sm:flex-row sm:items-center">
        <Link to="/submit" className="btn-primary">
          <Icon name="upload_file" className="text-[20px]" /> Submit Another Task
        </Link>
        {s.ai_feedback && s.grading_status === 'done' && <CopyButton text={feedbackText(s)} />}
      </section>

      {history.length > 1 && (
        <section className="card p-6">
          <h2 className="mb-3 text-headline-md text-ink">Your reviewed submissions</h2>
          <ul className="divide-y divide-slate-100">
            {history.map((h) => (
              <li key={h.id}>
                <Link to={`/grading/${h.id}`} className={`flex items-center gap-3 py-3 hover:text-primary-container ${h.id === s.id ? 'text-primary-container' : 'text-ink'}`}>
                  <span className="w-12 font-mono text-label-md text-on-surface-variant">D{h.day_number}</span>
                  <Icon name={h.submission_type === 'article' ? 'article' : 'code'} className="text-[18px] text-on-surface-variant" />
                  <span className="min-w-0 flex-1 truncate">{submissionTitle(h)}</span>
                  <span className="font-mono text-label-md">
                    {h.grading_status === 'pending' ? 'grading…' : h.grading_status === 'failed' ? 'failed' : h.ai_score !== null ? `${h.ai_score}/10` : 'reviewed'}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function feedbackText(s: Submission): string {
  const d = s.ai_details
  return [
    `${submissionTitle(s)}${s.ai_score !== null ? ` - ${s.ai_score}/10` : ''}`,
    s.ai_feedback,
    d?.strengths?.length ? `Strengths:\n${d.strengths.map((x) => `- ${x}`).join('\n')}` : '',
    d?.improvements?.length ? `Improvements:\n${d.improvements.map((x) => `- ${x}`).join('\n')}` : '',
  ]
    .filter(Boolean)
    .join('\n\n')
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      className="btn-secondary"
      onClick={() =>
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        })
      }
    >
      <Icon name={copied ? 'check' : 'content_copy'} className="text-[20px]" /> {copied ? 'Copied' : 'Copy feedback'}
    </button>
  )
}

function ArticleResult({ s }: { s: Submission }) {
  const score = s.ai_score ?? 0
  const v = verdict(score)
  const strengths = s.ai_details?.strengths ?? []
  const improvements = s.ai_details?.improvements ?? []
  return (
    <>
      <section className="card grid gap-6 p-6 lg:grid-cols-[auto_1fr] lg:items-center">
        <div className="flex items-center gap-6">
          <ScoreRing value={score} color={v.color} label={Number.isInteger(score) ? score : score.toFixed(1)} sub="out of 10" />
          <div className="flex flex-col gap-2">
            <span className={`pill w-fit font-bold ${v.cls}`}>
              <Icon name="verified" className="text-[14px]" /> {v.label}
            </span>
            <p className="font-mono text-label-md text-secondary">+{s.points_awarded} pts earned</p>
            <p className="max-w-[220px] text-body-sm text-on-surface-variant">
              {s.counts_for_streak ? 'Base points plus a bonus scaled from this grade.' : 'Extra submission for the day: feedback only.'}
            </p>
          </div>
        </div>
        <div className="rounded-xl bg-surface-container-low p-5">
          <p className="flex items-center gap-2 font-mono text-label-sm tracking-wider text-ink uppercase">
            <span className="h-1.5 w-1.5 rounded-full bg-secondary" /> Overall feedback
          </p>
          <p className="mt-2 text-body-lg text-ink">“{s.ai_feedback}”</p>
        </div>
      </section>

      {s.ai_breakdown && (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {RUBRIC.map((r) => {
            const val = s.ai_breakdown![r.key] ?? 0
            return (
              <div key={r.key} className="card flex flex-col gap-3 p-5">
                <div className="flex items-start justify-between">
                  <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${r.tint}`}>
                    <Icon name={r.icon} className="text-[20px]" />
                  </span>
                  <span className="font-mono">
                    <span className="text-headline-md font-bold text-ink">{val}</span>
                    <span className="text-on-surface-variant"> / {r.max}</span>
                  </span>
                </div>
                <div>
                  <p className="font-semibold text-ink">{r.name}</p>
                  <p className="text-body-sm text-on-surface-variant">{r.desc}</p>
                </div>
                <div className="mt-auto">
                  <div className="mb-1 flex justify-between font-mono text-label-sm text-on-surface-variant">
                    <span>Score</span>
                    <span>{Math.round((val / r.max) * 100)}%</span>
                  </div>
                  <ProgressBar value={(val / r.max) * 100} className={r.bar} />
                </div>
              </div>
            )
          })}
        </section>
      )}

      {(strengths.length > 0 || improvements.length > 0) && (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-headline-md text-ink">
                <Icon name="thumb_up" className="text-secondary" /> Strengths
              </h2>
              <span className="pill bg-surface-container-low text-on-surface-variant">{strengths.length} highlights</span>
            </div>
            <ul className="flex flex-col gap-3">
              {strengths.map((x, i) => (
                <li key={i} className="flex gap-3 rounded-xl bg-surface-container-low p-4">
                  <Icon name="check_circle" className="text-secondary" />
                  <span className="text-body-md text-ink">{x}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-headline-md text-ink">
                <Icon name="upgrade" className="text-tertiary" /> Suggested Improvements
              </h2>
              <span className="pill bg-streak-bg text-streak-text">{improvements.length} action items</span>
            </div>
            <ol className="flex flex-col gap-3">
              {improvements.map((x, i) => (
                <li key={i} className="flex gap-3 rounded-xl bg-surface-container-low p-4">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-streak-bg font-mono text-label-sm font-bold text-streak-text">
                    {i + 1}
                  </span>
                  <span className="text-body-md text-ink">{x}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </>
  )
}

function CodeResult({ s }: { s: Submission }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="card p-6">
        <p className="flex items-center gap-2 font-mono text-label-sm tracking-wider text-ink uppercase">
          <Icon name="psychology" className="text-[16px] text-primary-container" /> Reviewer comments
        </p>
        <p className="mt-3 text-body-lg text-ink">{s.ai_feedback}</p>
        <p className="mt-4 text-body-sm text-on-surface-variant">Code reviews are feedback only and don't change your points.</p>
      </section>
      <section className="overflow-hidden rounded-2xl bg-[#0f172a] shadow-lift">
        <div className="flex items-center gap-3 border-b border-white/5 bg-[#1e293b] px-4 py-2.5">
          <span className="flex gap-1.5">
            <span className="h-3 w-3 rounded-full bg-[#ef4444]" />
            <span className="h-3 w-3 rounded-full bg-[#f59e0b]" />
            <span className="h-3 w-3 rounded-full bg-[#10b981]" />
          </span>
          <span className="font-mono text-label-md text-slate-300">
            day-{s.day_number} · {s.language}
          </span>
        </div>
        <pre className="max-h-[420px] overflow-auto p-4 font-mono text-label-md leading-[22px] text-[#f8fafc]">{s.content}</pre>
      </section>
    </div>
  )
}

function PendingState() {
  return (
    <section className="card p-6">
      <div className="flex items-center gap-3 text-primary-container">
        <Icon name="progress_activity" className="animate-spin" />
        <p className="font-medium">Grading in progress. This usually takes under a minute; the page updates on its own.</p>
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-[132px_1fr]">
        <div className="skeleton h-[132px] w-[132px] rounded-full!" />
        <div className="flex flex-col gap-3">
          <div className="skeleton h-4 w-1/3" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-4 w-5/6" />
          <div className="skeleton h-4 w-2/3" />
        </div>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton h-28" />
        ))}
      </div>
    </section>
  )
}
