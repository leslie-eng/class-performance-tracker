import { useState, type FormEvent } from 'react'
import { validateProposal, type ProposalErrors } from '../lib/challenges'
import type { ProposalInput, TaskTypes } from '../lib/types'
import { ErrorBanner } from './ui'

/** Propose or edit a challenge. Checks the same rules as the API before sending; the API still decides. */
export function ProposalForm({
  initial,
  today,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial: ProposalInput
  today: string
  submitLabel: string
  pending: boolean
  error: unknown
  onSubmit: (values: ProposalInput) => void
  onCancel: () => void
}) {
  const [f, setF] = useState(initial)
  const [errors, setErrors] = useState<ProposalErrors>({})
  const set = <K extends keyof ProposalInput>(k: K, v: ProposalInput[K]) => {
    setF((s) => ({ ...s, [k]: v }))
    setErrors((e) => ({ ...e, [k]: undefined }))
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const found = validateProposal(f, today, f.start_date !== initial.start_date || !initial.name)
    setErrors(found)
    if (Object.keys(found).length) return
    onSubmit({ ...f, name: f.name.trim(), description: f.description?.trim() || null })
  }

  const field = (k: keyof ProposalInput) => ({
    'aria-invalid': errors[k] ? true : undefined,
    'aria-describedby': errors[k] ? `proposal-${k}-error` : undefined,
  })
  const message = (k: keyof ProposalInput) =>
    errors[k] && (
      <span id={`proposal-${k}-error`} className="text-body-sm text-error">
        {errors[k]}
      </span>
    )

  return (
    <form className="grid gap-4 sm:grid-cols-2" onSubmit={submit} noValidate>
      <label className="flex flex-col gap-1.5 sm:col-span-2">
        <span className="label">Name</span>
        <input className="input" value={f.name} maxLength={200} onChange={(e) => set('name', e.target.value)} placeholder="30 Days of SQL" {...field('name')} />
        {message('name')}
      </label>
      <label className="flex flex-col gap-1.5 sm:col-span-2">
        <span className="label">What members do each day (optional)</span>
        <textarea className="input min-h-20" value={f.description ?? ''} maxLength={2000} onChange={(e) => set('description', e.target.value)} placeholder="One SQL problem or a short write-up a day" {...field('description')} />
        {message('description')}
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="label">Start date</span>
        <input className="input" type="date" min={today} value={f.start_date} onChange={(e) => set('start_date', e.target.value)} {...field('start_date')} />
        {message('start_date')}
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="label">End date</span>
        <input className="input" type="date" min={f.start_date || today} value={f.end_date} onChange={(e) => set('end_date', e.target.value)} {...field('end_date')} />
        {message('end_date')}
      </label>
      <label className="flex flex-col gap-1.5 sm:col-span-2">
        <span className="label">Task types</span>
        <select className="input" value={f.task_types_allowed} onChange={(e) => set('task_types_allowed', e.target.value as TaskTypes)}>
          <option value="both">Code + articles</option>
          <option value="code">Code only</option>
          <option value="article">Articles only</option>
        </select>
      </label>
      <p className="text-body-sm text-on-surface-variant sm:col-span-2">
        Points and streak rules use the group's defaults; an admin can adjust them when approving.
      </p>
      <div className="flex flex-col gap-3 sm:col-span-2">
        <ErrorBanner error={error} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </button>
          <button className="btn-primary" disabled={pending}>
            {submitLabel}
          </button>
        </div>
      </div>
    </form>
  )
}
