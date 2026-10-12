import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api } from '../lib/api'
import { shortDate } from '../lib/dates'
import { keys } from '../lib/queries'
import type { Brief } from '../lib/types'
import { ErrorBanner, Icon, Spinner } from './ui'

/** Notes for the next Friday Drop. Any member or admin can paste them. */
export function ClassNotesForm() {
  const brief = useQuery({ queryKey: ['weekly', 'brief'], queryFn: () => api<Brief | null>('/weekly/brief') })
  if (brief.isLoading) return <Spinner />
  return <NotesEditor brief={brief.data ?? null} />
}

function NotesEditor({ brief }: { brief: Brief | null }) {
  const qc = useQueryClient()
  const [notes, setNotes] = useState(brief?.source_notes ?? '')
  const [saved, setSaved] = useState(false)
  const save = useMutation({
    mutationFn: () => api<Brief>('/weekly/brief', { method: 'PUT', json: { source_notes: notes } }),
    onSuccess: (b) => {
      setSaved(true)
      qc.setQueryData(['weekly', 'brief'], { ...b, source_notes: notes })
      qc.invalidateQueries({ queryKey: keys.weekly })
      // The summary is generated in the background; pick it up shortly.
      setTimeout(() => qc.invalidateQueries({ queryKey: ['weekly', 'brief'] }), 8000)
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    setSaved(false)
    save.mutate()
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={submit}>
      <label className="flex flex-col gap-1.5">
        <span className="label">
          Class notes for the drop{brief ? ` on ${shortDate(brief.week_key)}` : ''}
        </span>
        <textarea
          className="input h-auto min-h-40 py-2 font-mono text-label-md"
          value={notes}
          onChange={(e) => {
            setNotes(e.target.value)
            setSaved(false)
          }}
          placeholder="Paste this week's class notes: topics covered, key definitions, examples…"
          minLength={20}
          maxLength={50000}
          required
        />
      </label>
      {brief?.summary && (
        <div className="rounded-lg bg-surface-container-low p-3 text-body-sm text-on-surface-variant">
          <p className="label mb-1">Generated summary</p>
          {brief.summary}
        </div>
      )}
      {brief?.summary_error && <p className="text-body-sm text-error">{brief.summary_error}</p>}
      <ErrorBanner error={save.error} />
      <div className="flex items-center justify-end gap-3">
        {saved && (
          <span className="flex items-center gap-1 text-body-md text-secondary">
            <Icon name="check" className="text-[18px]" /> Saved, summarising…
          </span>
        )}
        <button className="btn-primary" disabled={save.isPending || notes.trim().length < 20}>
          Save notes
        </button>
      </div>
    </form>
  )
}
