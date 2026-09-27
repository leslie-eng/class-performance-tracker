import { useMutation } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { RulesModal } from '../components/RulesModal'
import { ErrorBanner, Icon, PageLoader } from '../components/ui'
import { api } from '../lib/api'
import { dateForDay, dayNumber, formatCountdown, relativeTime, shortDate } from '../lib/dates'
import { useInvalidateProgress, useLeaderboard, useMySubmissions } from '../lib/queries'
import { useSession } from '../lib/session'
import { LANGUAGES, articleHost } from '../lib/submissions'
import type { Submission, SubmissionType } from '../lib/types'
import { useCountdown } from '../lib/useCountdown'

const EXT: Record<string, string> = {
  python: 'py', sql: 'sql', javascript: 'js', typescript: 'ts', java: 'java', go: 'go', rust: 'rs',
  c: 'c', cpp: 'cpp', csharp: 'cs', bash: 'sh', other: 'txt',
}

interface Draft {
  type: SubmissionType
  code: string
  language: string
  problemLink: string
  url: string
  savedAt?: string
}

const EMPTY: Draft = { type: 'code', code: '', language: 'python', problemLink: '', url: '' }

function loadDraft(key: string): Draft {
  try {
    return { ...EMPTY, ...JSON.parse(localStorage.getItem(key) ?? '{}') }
  } catch {
    return EMPTY
  }
}

export default function SubmitPage() {
  const { user, challenge, meta } = useSession()
  const subs = useMySubmissions(challenge?.id)
  const board = useLeaderboard(challenge?.id)
  const invalidate = useInvalidateProgress()
  const navigate = useNavigate()
  const secs = useCountdown(meta?.timezone)

  const draftKey = `classtrack.draft.${challenge?.id}`
  const [draft, setDraft] = useState<Draft>(() => loadDraft(draftKey))
  const [savedAt, setSavedAt] = useState<string | undefined>(draft.savedAt)
  const [showRules, setShowRules] = useState(false)

  const today = meta?.today
  const todayDay = challenge && today ? dayNumber(challenge, today) : 0
  const [day, setDay] = useState<number | null>(null)

  // Only allow the task types the challenge accepts.
  const allowed = challenge?.task_types_allowed ?? 'both'
  const type: SubmissionType = allowed === 'both' ? draft.type : allowed

  // Autosave the draft a moment after typing stops.
  useEffect(() => {
    const t = setTimeout(() => {
      const stamp = new Date().toISOString()
      try {
        localStorage.setItem(draftKey, JSON.stringify({ ...draft, savedAt: stamp }))
        if (draft.code || draft.url) setSavedAt(stamp)
      } catch {
        /* storage unavailable */
      }
    }, 800)
    return () => clearTimeout(t)
  }, [draft, draftKey])

  const doneDays = useMemo(
    () => new Set((subs.data ?? []).filter((s) => s.counts_for_streak).map((s) => s.day_number)),
    [subs.data],
  )

  const submit = useMutation({
    mutationFn: () =>
      api<Submission>('/submissions', {
        method: 'POST',
        json: {
          challenge_id: challenge!.id,
          submission_type: type,
          day_number: selectedDay,
          ...(type === 'code'
            ? { content: draft.code, language: draft.language, problem_link: draft.problemLink.trim() || null }
            : { content: draft.url.trim() }),
        },
      }),
    onSuccess: async (sub) => {
      try {
        localStorage.removeItem(draftKey)
      } catch {
        /* ignore */
      }
      await invalidate()
      navigate(sub.grading_status === 'not_applicable' ? '/?submitted=1' : `/grading/${sub.id}`)
    },
  })

  if (!challenge || !meta || !user || subs.isLoading) return <PageLoader />

  const rules = challenge.effective_rules
  const inWindow = todayDay >= 1 && todayDay <= challenge.total_days + rules.backfill_days
  const dayOptions = Array.from({ length: rules.backfill_days + 1 }, (_, i) => todayDay - i).filter(
    (d) => d >= 1 && d <= challenge.total_days,
  )
  const selectedDay = day ?? dayOptions[0] ?? todayDay
  const alreadyCounted = doneDays.has(selectedDay)
  const streak = board.data?.find((r) => r.user_id === user.id)?.current_streak ?? 0
  const lines = draft.code.split('\n').length
  const ptsAvailable = type === 'code' ? rules.code_points : rules.article_points + rules.article_ai_bonus_max
  const update = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))
  const canSubmit = type === 'code' ? draft.code.trim().length > 0 : /^https?:\/\/\S+\.\S+/.test(draft.url.trim())

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (canSubmit) submit.mutate()
  }

  if (!inWindow || dayOptions.length === 0) {
    return (
      <div className="card mx-auto max-w-xl p-8 text-center">
        <Icon name="event_busy" className="text-[40px] text-on-surface-variant" />
        <h1 className="mt-2 text-headline-md text-ink">No open day to submit for</h1>
        <p className="mt-1 text-on-surface-variant">
          {todayDay < 1 ? `${challenge.name} starts on ${challenge.start_date}.` : `${challenge.name} ended on ${challenge.end_date}.`}
        </p>
        <Link to="/" className="btn-primary mt-6">Back to dashboard</Link>
      </div>
    )
  }

  return (
    <form className="flex flex-col gap-6" onSubmit={onSubmit}>
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <nav className="mb-2 flex items-center gap-1 text-body-md text-on-surface-variant">
            <Icon name="folder_open" className="text-[18px]" /> Challenges / {challenge.name} / <span className="text-ink">Submit Task</span>
          </nav>
          <h1 className="text-headline-lg text-ink md:text-[28px]">Daily Task Submission</h1>
          <p className="text-body-md text-on-surface-variant">Log today's build or article and lock in your streak.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <div className="flex items-center gap-2 rounded-xl bg-streak-bg px-4 py-2 text-streak-text">
            <Icon name="local_fire_department" filled className="text-[24px] text-streak" />
            <div className="font-mono leading-tight">
              <p className="text-label-sm uppercase">Active streak</p>
              <p className="text-label-md font-bold">{streak} Days</p>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-xl bg-primary-fixed px-4 py-2 text-primary-container">
            <Icon name="timer" className="text-[24px]" />
            <div className="font-mono leading-tight">
              <p className="text-label-sm uppercase">Today's cutoff</p>
              <p className="text-label-md font-bold">Due in {formatCountdown(secs)}</p>
            </div>
          </div>
        </div>
      </div>

      <section className="flex flex-col gap-4 rounded-2xl bg-surface-container-low p-5 shadow-card md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-4">
          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-primary-container font-mono text-headline-md font-bold text-white">
            D{selectedDay}
          </span>
          <div>
            <p className="font-mono text-label-sm text-on-surface-variant uppercase">
              {challenge.name} · {shortDate(dateForDay(challenge, selectedDay))}
            </p>
            <p className="text-headline-md text-ink">
              Day {selectedDay} of {challenge.total_days}
            </p>
            {challenge.description && <p className="text-body-md text-on-surface-variant">{challenge.description}</p>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-secondary h-8 text-body-md" onClick={() => setShowRules(true)}>
            <Icon name="description" className="text-[18px]" /> Rules & scoring
          </button>
          {alreadyCounted ? (
            <span className="pill bg-surface-container-high text-on-surface-variant">Day already counted</span>
          ) : (
            <span className="pill bg-secondary-container font-bold text-on-secondary-container">● up to {ptsAvailable} pts</span>
          )}
        </div>
      </section>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div role="tablist" className="inline-flex rounded-xl bg-surface-container p-1">
          {(['code', 'article'] as const).map((t) => {
            const disabled = allowed !== 'both' && allowed !== t
            return (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={type === t}
                disabled={disabled}
                onClick={() => update({ type: t })}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 font-mono text-label-md transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${type === t ? 'bg-white text-primary-container shadow-card' : 'text-on-surface-variant hover:text-ink'}`}
              >
                <Icon name={t === 'code' ? 'terminal' : 'article'} className="text-[18px]" />
                {t === 'code' ? 'Code Submission' : 'Article'}
                <span className="rounded bg-surface-container-high px-1.5 text-label-sm">
                  +{t === 'code' ? rules.code_points : rules.article_points} pts
                </span>
              </button>
            )
          })}
        </div>
        <span className="flex items-center gap-1.5 font-mono text-label-sm text-on-surface-variant">
          <span className="h-1.5 w-1.5 rounded-full bg-secondary" />
          {savedAt ? `Draft saved on this device ${relativeTime(savedAt)}` : 'Drafts auto-save on this device'}
        </span>
      </div>

      <div className={`grid gap-4 ${type === 'code' ? 'md:grid-cols-[1fr_1fr_1.4fr]' : 'md:grid-cols-[1fr_2fr]'}`}>
        <label className="flex flex-col gap-1.5">
          <span className="label flex items-center gap-1">
            <Icon name="calendar_today" className="text-[14px]" /> Counts for day
          </span>
          <select className="input" value={selectedDay} onChange={(e) => setDay(Number(e.target.value))}>
            {dayOptions.map((d) => (
              <option key={d} value={d}>
                Day {d} {d === todayDay ? '(today)' : `(${shortDate(dateForDay(challenge, d))})`}
                {doneDays.has(d) ? ' ✓ done' : ''}
              </option>
            ))}
          </select>
        </label>
        {type === 'code' ? (
          <>
            <label className="flex flex-col gap-1.5">
              <span className="label flex items-center gap-1">
                <Icon name="code" className="text-[14px]" /> Language
              </span>
              <select className="input" value={draft.language} onChange={(e) => update({ language: e.target.value })}>
                {LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="label flex items-center gap-1">
                <Icon name="link" className="text-[14px]" /> Problem link (optional)
              </span>
              <input
                className="input font-mono text-label-md"
                type="url"
                placeholder="https://leetcode.com/problems/…"
                value={draft.problemLink}
                onChange={(e) => update({ problemLink: e.target.value })}
              />
            </label>
          </>
        ) : (
          <label className="flex flex-col gap-1.5">
            <span className="label flex items-center gap-1">
              <Icon name="link" className="text-[14px]" /> Article URL
            </span>
            <input
              className="input font-mono text-label-md"
              type="url"
              required
              placeholder="https://dev.to/you/your-article"
              value={draft.url}
              onChange={(e) => update({ url: e.target.value })}
            />
          </label>
        )}
      </div>

      {type === 'code' ? (
        <CodeEditor
          value={draft.code}
          onChange={(code) => update({ code })}
          filename={`day-${selectedDay}.${EXT[draft.language] ?? 'txt'}`}
          language={draft.language}
          lines={lines}
        />
      ) : (
        <ArticlePanel url={draft.url} rules={rules} />
      )}

      <ErrorBanner error={submit.error} />

      <div className="flex flex-col gap-3 border-t border-slate-200 pt-6 md:flex-row md:items-center md:justify-between">
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            setDraft(EMPTY)
            setSavedAt(undefined)
          }}
        >
          <Icon name="restart_alt" className="text-[20px]" /> Clear draft
        </button>
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <p className={`rounded-lg px-4 py-2 font-mono text-label-sm ${alreadyCounted ? 'bg-surface-container text-on-surface-variant' : 'bg-streak-bg text-streak-text'}`}>
            {alreadyCounted
              ? `Day ${selectedDay} already counts. This one is extra: feedback only, no points.`
              : type === 'article'
                ? 'Articles are graded by AI right after you submit'
                : `Earns ${rules.code_points} pts and keeps your streak going`}
          </p>
          <button className="btn-primary h-12 px-6 text-body-lg" disabled={!canSubmit || submit.isPending}>
            <Icon name="rocket_launch" className="text-[22px]" />
            {submit.isPending ? 'Submitting…' : `Submit Task (Day ${selectedDay})`}
          </button>
        </div>
      </div>

      {showRules && <RulesModal challenge={challenge} onClose={() => setShowRules(false)} />}
    </form>
  )
}

function CodeEditor({
  value,
  onChange,
  filename,
  language,
  lines,
}: {
  value: string
  onChange: (v: string) => void
  filename: string
  language: string
  lines: number
}) {
  const gutter = useRef<HTMLDivElement>(null)
  const [cursor, setCursor] = useState({ ln: 1, col: 1 })

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== 'Tab') return
    e.preventDefault()
    const el = e.currentTarget
    const { selectionStart: s, selectionEnd: end } = el
    onChange(value.slice(0, s) + '    ' + value.slice(end))
    requestAnimationFrame(() => el.setSelectionRange(s + 4, s + 4))
  }

  function trackCursor(el: HTMLTextAreaElement) {
    const before = el.value.slice(0, el.selectionStart).split('\n')
    setCursor({ ln: before.length, col: before.at(-1)!.length + 1 })
  }

  return (
    <div className="overflow-hidden rounded-2xl bg-[#0f172a] shadow-lift">
      <div className="flex items-center gap-4 border-b border-white/5 bg-[#1e293b] px-4 py-2.5">
        <span className="flex gap-1.5">
          <span className="h-3 w-3 rounded-full bg-[#ef4444]" />
          <span className="h-3 w-3 rounded-full bg-[#f59e0b]" />
          <span className="h-3 w-3 rounded-full bg-[#10b981]" />
        </span>
        <span className="rounded-md bg-white/5 px-3 py-1 font-mono text-label-md text-slate-200">{filename}</span>
      </div>
      <div className="flex max-h-[520px] min-h-[320px] overflow-hidden">
        <div ref={gutter} aria-hidden className="w-12 shrink-0 overflow-hidden py-4 pr-3 text-right font-mono text-label-md leading-[22px] text-[#475569] select-none">
          {Array.from({ length: Math.max(lines, 14) }, (_, i) => (
            <div key={i}>{i + 1}</div>
          ))}
        </div>
        <textarea
          aria-label="Code"
          className="min-h-[320px] flex-1 resize-none bg-transparent py-4 pr-4 font-mono text-label-md leading-[22px] whitespace-pre text-[#f8fafc] caret-[#60a5fa] outline-none placeholder:text-slate-600"
          spellCheck={false}
          value={value}
          placeholder={'# Paste or write your solution for today\n'}
          onChange={(e) => {
            onChange(e.target.value)
            trackCursor(e.target)
          }}
          onKeyDown={onKeyDown}
          onKeyUp={(e) => trackCursor(e.currentTarget)}
          onClick={(e) => trackCursor(e.currentTarget)}
          onScroll={(e) => {
            if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop
          }}
        />
      </div>
      <div className="flex items-center justify-between border-t border-white/5 bg-[#1e293b] px-4 py-2 font-mono text-label-sm text-slate-400">
        <span className="flex items-center gap-4">
          <span className="flex items-center gap-1.5 text-[#4ade80]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#4ade80]" /> {language}
          </span>
          <span>UTF-8</span>
          <span>{value.length.toLocaleString()} chars</span>
        </span>
        <span>
          Ln {cursor.ln}, Col {cursor.col}
        </span>
      </div>
    </div>
  )
}

function ArticlePanel({ url, rules }: { url: string; rules: { article_points: number; article_ai_bonus_max: number } }) {
  const valid = /^https?:\/\/\S+\.\S+/.test(url.trim())
  const rubric = [
    ['Clarity', 3, 'Easy to follow for someone learning the topic'],
    ['Technical accuracy', 3, 'Claims and code examples are correct'],
    ['Depth', 2, 'Goes beyond a surface-level tutorial recap'],
    ['Originality', 2, 'Your own examples and insights'],
  ] as const
  return (
    <div className="grid gap-4 md:grid-cols-[1.2fr_1fr]">
      <div className="card flex flex-col justify-center gap-3 p-6">
        {valid ? (
          <>
            <p className="label">Article preview</p>
            <p className="flex items-center gap-2 text-headline-md text-ink">
              <Icon name="public" className="text-primary-container" /> {articleHost(url)}
            </p>
            <a href={url} target="_blank" rel="noreferrer" className="truncate font-mono text-label-md text-primary-container hover:underline">
              {url}
            </a>
            <p className="text-body-md text-on-surface-variant">
              The page must be publicly readable (no login wall) so the grader can fetch it.
            </p>
          </>
        ) : (
          <div className="flex items-center gap-3 text-on-surface-variant">
            <Icon name="newspaper" className="text-[32px]" />
            <p>Paste the link to your published article (Medium, dev.to, Hashnode, LinkedIn, your blog…).</p>
          </div>
        )}
      </div>
      <div className="card p-6">
        <p className="label flex items-center gap-1">
          <Icon name="psychology" className="text-[16px]" /> How the AI grades it
        </p>
        <ul className="mt-3 flex flex-col gap-2.5">
          {rubric.map(([name, max, desc]) => (
            <li key={name} className="flex items-start justify-between gap-3">
              <span>
                <span className="font-medium text-ink">{name}</span>
                <span className="block text-body-sm text-on-surface-variant">{desc}</span>
              </span>
              <span className="pill shrink-0 bg-surface-container text-on-surface">0–{max}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 rounded-lg bg-secondary-container/40 px-3 py-2 text-body-sm text-on-secondary-container">
          {rules.article_points} pts for submitting + up to {rules.article_ai_bonus_max} bonus pts from the grade.
        </p>
      </div>
    </div>
  )
}
