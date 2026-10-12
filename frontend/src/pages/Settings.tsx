import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ErrorBanner, Icon, PageLoader } from '../components/ui'
import { api } from '../lib/api'
import { keys } from '../lib/queries'
import { useSession } from '../lib/session'
import type { User } from '../lib/types'

export default function SettingsPage() {
  const { user } = useSession()
  if (!user) return <PageLoader />
  return <SettingsForm user={user} />
}

function SettingsForm({ user }: { user: User }) {
  const qc = useQueryClient()
  const [name, setName] = useState(user.name)
  const [phone, setPhone] = useState(user.phone_number ?? '')
  const [optIn, setOptIn] = useState(user.whatsapp_opt_in)
  const [specialization, setSpecialization] = useState(user.specialization ?? '')
  const { meta } = useSession()
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      api<User>('/auth/me', {
        method: 'PATCH',
        json: {
          name: name.trim(),
          phone_number: phone.trim() || null,
          whatsapp_opt_in: optIn && !!phone.trim(),
          specialization: specialization || null,
        },
      }),
    onSuccess: (u) => {
      qc.setQueryData(keys.me, u)
      qc.invalidateQueries({ queryKey: ['leaderboard'] })
      setSaved(true)
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    setSaved(false)
    save.mutate()
  }

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-headline-lg text-ink">Settings</h1>
      <form className="card mt-6 flex flex-col gap-5 p-6" onSubmit={submit}>
        <label className="flex flex-col gap-1.5">
          <span className="label">Display name</span>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Email</span>
          <input className="input bg-surface-container-low" value={user.email} disabled />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="label">Specialization</span>
          <select className="input" value={specialization} onChange={(e) => setSpecialization(e.target.value)}>
            <option value="">Not set (general)</option>
            {(meta?.specializations ?? []).map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
          <span className="text-body-sm text-on-surface-variant">Sets the topic of your monthly interview-prep quiz.</span>
        </label>
        <div className="flex flex-col gap-3 rounded-xl bg-surface-container-low p-4">
          <p className="flex items-center gap-2 font-semibold text-ink">
            <Icon name="chat" className="text-secondary" /> WhatsApp nudges
          </p>
          <p className="text-body-md text-on-surface-variant">
            The Friday Drop every week, and a reminder if you miss a couple of days in a row.
          </p>
          <label className="flex flex-col gap-1.5">
            <span className="label">Phone number (with country code)</span>
            <input className="input" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+254700000000" pattern="^\+?[1-9]\d{7,14}$" />
          </label>
          <label className="flex items-center gap-2 text-body-md text-ink">
            <input type="checkbox" className="h-[18px] w-[18px] accent-[#22c55e]" checked={optIn && !!phone.trim()} disabled={!phone.trim()} onChange={(e) => setOptIn(e.target.checked)} />
            Send me WhatsApp messages
          </label>
        </div>
        <ErrorBanner error={save.error} />
        <div className="flex items-center justify-end gap-3">
          {saved && (
            <span className="flex items-center gap-1 text-body-md text-secondary">
              <Icon name="check" className="text-[18px]" /> Saved
            </span>
          )}
          <button className="btn-primary" disabled={save.isPending}>
            Save changes
          </button>
        </div>
      </form>
    </div>
  )
}
