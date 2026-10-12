import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../lib/api'
import type { LLMConfig, LLMModel, LLMTask, LLMTestResult, LLMUsage } from '../../lib/types'
import { ErrorBanner, Icon, Spinner } from '../ui'

const llmKey = ['admin', 'llm'] as const

const TASKS: Record<LLMTask, { title: string; detail: string }> = {
  grading: { title: 'Grading', detail: 'Article scores, short quiz answers' },
  feedback: { title: 'Feedback', detail: 'Comments on daily code and exercise attempts' },
  summary: { title: 'Summaries', detail: 'Weekly class-notes summary, material digests' },
  generation: { title: 'Generation', detail: 'Quizzes and coding exercises' },
}

const SOURCE: Record<LLMConfig['tasks'][number]['source'], string> = {
  admin: 'set here',
  env: 'from LLM_TASK_MODELS',
  default: 'LLM_DEFAULT_MODEL',
}

const price = (m: LLMModel) => (m.tier === 'free' ? 'free' : `$${m.prompt_price} / $${m.completion_price} per M tokens`)
const money = (n: number) => (n === 0 ? '$0' : n < 0.01 ? `$${n.toFixed(5)}` : `$${n.toFixed(3)}`)

/** Admin: pick the model for each AI task (applies within seconds, no redeploy) and try a model out. */
export function AIModels() {
  const qc = useQueryClient()
  const config = useQuery({ queryKey: llmKey, queryFn: () => api<LLMConfig>('/admin/llm') })
  const setModel = useMutation({
    mutationFn: ({ task, model }: { task: LLMTask; model: string | null }) =>
      api<LLMConfig>(`/admin/llm/tasks/${task}`, { method: 'PUT', json: { model } }),
    onSuccess: (data) => qc.setQueryData(llmKey, data),
  })

  const c = config.data
  const byId = new Map(c?.models.map((m) => [m.id, m]))
  return (
    <section className="card p-6 xl:col-span-2">
      <h2 className="flex items-center gap-2 text-headline-md text-ink">
        <Icon name="smart_toy" className="text-primary-container" /> AI models
      </h2>
      <p className="mt-1 text-body-md text-on-surface-variant">
        Choose the model for each kind of AI work. Changes apply within seconds. Only models with a zero-data-retention provider
        can handle member data; free models are for the test button only.
      </p>
      {config.isLoading && <Spinner className="mt-4" />}
      <ErrorBanner error={config.error ?? setModel.error} />
      {c && !c.configured && (
        <p className="mt-3 rounded-lg bg-tertiary-fixed px-3 py-2 text-body-sm text-tertiary">
          OPENROUTER_API_KEY isn't set on the server, so AI features are off. You can still choose models now.
        </p>
      )}
      {c && (
        <div className="mt-4 grid gap-6 lg:grid-cols-2">
          <div>
            <ul className="flex flex-col divide-y divide-slate-100">
              {c.tasks.map((t) => (
                <li key={t.task} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{TASKS[t.task].title}</p>
                    <p className="text-body-sm text-on-surface-variant">{TASKS[t.task].detail}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <select
                      aria-label={`Model for ${TASKS[t.task].title}`}
                      className="input h-9 w-full py-1 sm:w-56"
                      value={t.model_id}
                      disabled={setModel.isPending}
                      onChange={(e) => setModel.mutate({ task: t.task, model: e.target.value })}
                    >
                      {!byId.has(t.model_id) && <option value={t.model_id}>{t.model_id}</option>}
                      {c.models.map((m) => (
                        <option key={m.id} value={m.id} disabled={!m.allowed_for_member_data}>
                          {m.label}
                          {m.allowed_for_member_data ? '' : ' (testing only)'}
                        </option>
                      ))}
                    </select>
                    {t.source === 'admin' ? (
                      <button className="btn-ghost h-9 px-2 text-label-sm" title="Go back to the server's env setting"
                        disabled={setModel.isPending} onClick={() => setModel.mutate({ task: t.task, model: null })}>
                        Reset
                      </button>
                    ) : (
                      <span className="w-14 text-label-sm text-on-surface-variant" title={SOURCE[t.source]}>default</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-body-sm text-on-surface-variant">
              If a model fails or is rate-limited, OpenRouter tries: {c.fallbacks.map((id) => byId.get(id)?.label ?? id).join(' → ') || 'nothing'}.
            </p>
          </div>
          <TestModel models={c.models} />
        </div>
      )}
      {c && <Usage />}
    </section>
  )
}

function TestModel({ models }: { models: LLMModel[] }) {
  const [modelId, setModelId] = useState(models.find((m) => m.allowed_for_member_data)?.id ?? models[0]?.id ?? '')
  const [prompt, setPrompt] = useState('')
  const model = models.find((m) => m.id === modelId)
  const custom = !!model?.zdr
  const test = useMutation({
    mutationFn: () =>
      api<LLMTestResult>('/admin/llm/test', { method: 'POST', json: { model: modelId, prompt: custom && prompt.trim() ? prompt.trim() : null } }),
  })
  const r = test.data
  return (
    <div className="flex flex-col gap-3 rounded-xl bg-surface-container-low p-4">
      <p className="label">Test a model</p>
      <select aria-label="Model to test" className="input" value={modelId} onChange={(e) => { setModelId(e.target.value); test.reset() }}>
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label} · {price(m)}
          </option>
        ))}
      </select>
      {model && <p className="text-body-sm text-on-surface-variant">{model.notes}</p>}
      <textarea
        className="input min-h-20"
        maxLength={2000}
        disabled={!custom}
        placeholder={custom ? 'Optional prompt (leave blank for the sample). Never paste member data here.' : 'Uses the sample prompt: this model may log prompts.'}
        value={custom ? prompt : ''}
        onChange={(e) => setPrompt(e.target.value)}
      />
      <button className="btn-primary w-fit" disabled={!modelId || test.isPending} onClick={() => test.mutate()}>
        {test.isPending ? <Spinner /> : <Icon name="play_arrow" className="text-[18px]" />} Send test prompt
      </button>
      <ErrorBanner error={test.error} />
      {r && (
        <div className="flex flex-col gap-2">
          <p className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-label-sm text-on-surface-variant">
            <span>{models.find((m) => r.model_used.startsWith(m.id.split(':')[0]))?.label ?? r.model_used}</span>
            <span>{(r.latency_ms / 1000).toFixed(1)} s</span>
            <span>{r.tokens_in} in / {r.tokens_out} out</span>
            <span>{r.cost == null ? 'cost unknown' : `${money(r.cost)}${r.cost_estimated ? ' (est.)' : ''}`}</span>
          </p>
          <p className="rounded-lg bg-surface p-3 text-body-md whitespace-pre-wrap text-ink">{r.text || '(empty reply)'}</p>
        </div>
      )}
    </div>
  )
}

function Usage() {
  const [days, setDays] = useState(30)
  const usage = useQuery({ queryKey: [...llmKey, 'usage', days], queryFn: () => api<LLMUsage>(`/admin/llm/usage?days=${days}`) })
  const u = usage.data
  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="label">Usage and cost per model</p>
        <select aria-label="Period" className="input h-9 w-auto py-1" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>
      <ErrorBanner error={usage.error} />
      {u && (
        <>
          <p className="mt-2 text-body-sm text-on-surface-variant">
            {u.totals.calls} calls · {u.totals.errors} failed · {money(u.totals.cost)} total
          </p>
          {u.by_model.length > 0 ? (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-body-sm">
                <thead className="text-label-sm text-on-surface-variant">
                  <tr>
                    <th className="py-1 pr-3 font-medium">Model</th>
                    <th className="py-1 pr-3 text-right font-medium">Calls</th>
                    <th className="py-1 pr-3 text-right font-medium">Failed</th>
                    <th className="py-1 pr-3 text-right font-medium">As fallback</th>
                    <th className="py-1 pr-3 text-right font-medium">Tokens in / out</th>
                    <th className="py-1 pr-3 text-right font-medium">Cost</th>
                    <th className="py-1 pr-3 text-right font-medium">Per call</th>
                    <th className="py-1 text-right font-medium">Latency avg / p95</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-mono">
                  {u.by_model.map((g) => (
                    <tr key={g.name} title={g.error_types.length ? `Errors: ${g.error_types.join(', ')}` : g.name}>
                      <td className="py-1.5 pr-3 font-sans text-ink">{g.label}</td>
                      <td className="py-1.5 pr-3 text-right">{g.calls}</td>
                      <td className={`py-1.5 pr-3 text-right ${g.errors ? 'text-error' : ''}`}>{g.errors}</td>
                      <td className="py-1.5 pr-3 text-right">{g.fallbacks}</td>
                      <td className="py-1.5 pr-3 text-right">{g.tokens_in.toLocaleString()} / {g.tokens_out.toLocaleString()}</td>
                      <td className="py-1.5 pr-3 text-right">{money(g.cost)}{g.cost_estimated ? '*' : ''}</td>
                      <td className="py-1.5 pr-3 text-right">{money(g.cost_per_call)}</td>
                      <td className="py-1.5 text-right">{(g.avg_latency_ms / 1000).toFixed(1)} / {(g.p95_latency_ms / 1000).toFixed(1)} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {u.by_model.some((g) => g.cost_estimated) && (
                <p className="mt-1 text-label-sm text-on-surface-variant">* partly estimated from list prices</p>
              )}
            </div>
          ) : (
            <p className="mt-2 text-body-sm text-on-surface-variant">No AI calls in this period yet.</p>
          )}
        </>
      )}
    </div>
  )
}
