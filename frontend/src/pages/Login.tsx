import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ErrorBanner, Icon, Logo, Wordmark } from '../components/ui'
import { api, login } from '../lib/api'
import { useSession } from '../lib/session'

const FEATURES = [
  { icon: 'bolt', tint: 'bg-primary-fixed text-primary-container', title: 'Daily Task Log', body: 'Paste your code or link your article. Every day in the challenge is a slot to fill.' },
  { icon: 'local_fire_department', tint: 'bg-tertiary-fixed text-tertiary', title: 'Streak Momentum', body: 'Bonus points every 7 days in a row, and a cohort leaderboard to keep pace with.' },
  { icon: 'smart_toy', tint: 'bg-primary-fixed text-primary-container', title: 'Instant AI Review', body: 'Articles are graded on clarity, accuracy, depth and originality, with written feedback.' },
]

// Decorative contribution pattern for the welcome panel (not user data).
const PATTERN = Array.from({ length: 7 * 26 }, (_, i) => ((i * 37) % 11 < 8 ? ((i * 13) % 7 < 3 ? 4 : 3) : 0))
const HEAT = ['bg-heat-0', 'bg-heat-1', 'bg-heat-2', 'bg-heat-3', 'bg-heat-4']

export default function LoginPage() {
  const { token, signIn } = useSession()
  const navigate = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/'

  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [form, setForm] = useState({ name: '', email: '', password: '', phone: '', optIn: false })
  const [remember, setRemember] = useState(true)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  if (token) return <Navigate to={from} replace />

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'register') {
        await api('/auth/register', {
          method: 'POST',
          json: {
            name: form.name.trim(),
            email: form.email.trim(),
            password: form.password,
            phone_number: form.phone.trim() || null,
            whatsapp_opt_in: form.optIn && !!form.phone.trim(),
          },
        })
      }
      signIn(await login(form.email.trim(), form.password), remember)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto grid min-h-screen max-w-[1440px] items-center gap-10 px-4 py-10 md:px-margin lg:grid-cols-[1.2fr_1fr] lg:gap-16">
      <section className="flex flex-col gap-8">
        <div className="flex items-center gap-3">
          <Logo size={48} />
          <Wordmark className="text-[32px]" />
        </div>
        <div>
          <h1 className="text-[34px] leading-tight font-bold tracking-tight text-ink md:text-[46px]">
            Stay accountable.
            <br />
            <span className="text-primary-container">Build consistency.</span>
          </h1>
          <p className="mt-4 max-w-xl text-body-lg text-on-surface-variant">
            The study group tracker for 100 Days of Code style challenges: log daily tasks, keep your streak, and climb
            the cohort leaderboard.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="card p-5">
              <span className={`mb-4 flex h-10 w-10 items-center justify-center rounded-lg ${f.tint}`}>
                <Icon name={f.icon} filled className="text-[22px]" />
              </span>
              <p className="font-semibold text-ink">{f.title}</p>
              <p className="mt-1 text-body-md text-on-surface-variant">{f.body}</p>
            </div>
          ))}
        </div>
        <div className="card hidden p-5 sm:block">
          <div className="mb-3 flex items-center justify-between">
            <span className="label text-ink">Consistency, visualized</span>
            <span className="pill bg-secondary-container font-bold text-on-secondary-container">every day counts</span>
          </div>
          <div className="grid grid-flow-col grid-rows-7 gap-[4px] rounded-xl bg-surface-container-low p-4" style={{ gridAutoColumns: 'minmax(0, 1fr)' }}>
            {PATTERN.map((lvl, i) => (
              <span key={i} className={`aspect-square rounded-[3px] ${HEAT[lvl]}`} />
            ))}
          </div>
        </div>
      </section>

      <section className="card mx-auto w-full max-w-[520px] p-6 shadow-lift sm:p-10">
        <h2 className="text-[28px] font-bold tracking-tight text-ink">{mode === 'signin' ? 'Welcome back' : 'Join your cohort'}</h2>
        <p className="mt-1 text-body-lg text-on-surface-variant">
          {mode === 'signin' ? 'Sign in to keep your streak going' : 'Create an account to start logging tasks'}
        </p>

        <form className="mt-8 flex flex-col gap-4" onSubmit={submit}>
          {mode === 'register' && (
            <Field label="Full name" icon="person">
              <input className="input pl-10" required value={form.name} onChange={set('name')} autoComplete="name" placeholder="Maya Patel" />
            </Field>
          )}
          <Field label="Email" icon="mail">
            <input className="input pl-10" type="email" required value={form.email} onChange={set('email')} autoComplete="email" placeholder="you@example.com" />
          </Field>
          <Field label="Password" icon="key">
            <input
              className="input pr-10 pl-10"
              type={showPassword ? 'text' : 'password'}
              required
              minLength={mode === 'register' ? 8 : undefined}
              value={form.password}
              onChange={set('password')}
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            />
            <button
              type="button"
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-on-surface-variant hover:text-ink"
              onClick={() => setShowPassword((s) => !s)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              <Icon name={showPassword ? 'visibility_off' : 'visibility'} className="text-[20px]" />
            </button>
          </Field>
          {mode === 'register' && (
            <>
              <Field label="WhatsApp number (optional)" icon="call">
                <input className="input pl-10" type="tel" value={form.phone} onChange={set('phone')} placeholder="+254700000000" pattern="^\+?[1-9]\d{7,14}$" />
              </Field>
              <label className="flex items-center gap-2 text-body-md text-on-surface-variant">
                <input type="checkbox" className="h-[18px] w-[18px] accent-[#22c55e]" checked={form.optIn} onChange={set('optIn')} disabled={!form.phone.trim()} />
                Nudge me on WhatsApp if I fall behind
              </label>
            </>
          )}
          <label className="flex items-center gap-2 text-body-md text-on-surface-variant">
            <input type="checkbox" className="h-[18px] w-[18px] accent-[#22c55e]" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            Keep me signed in on this device
          </label>

          <ErrorBanner error={error} />

          <button className="btn-primary h-12 text-body-lg" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign In to Dashboard' : 'Create Account'}
            <Icon name="arrow_forward" className="text-[20px]" />
          </button>
        </form>

        <div className="mt-8 border-t border-slate-100 pt-6 text-center text-body-md text-on-surface-variant">
          {mode === 'signin' ? "Don't have an account? " : 'Already have an account? '}
          <button
            className="font-medium text-primary-container hover:underline"
            onClick={() => {
              setMode(mode === 'signin' ? 'register' : 'signin')
              setError(null)
            }}
          >
            {mode === 'signin' ? 'Create one' : 'Sign in'}
          </button>
        </div>
      </section>
    </div>
  )
}

function Field({ label, icon, children }: { label: string; icon: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-body-md font-medium text-ink">{label}</span>
      <span className="relative">
        <Icon name={icon} className="absolute top-1/2 left-3 -translate-y-1/2 text-[20px] text-on-surface-variant" />
        {children}
      </span>
    </label>
  )
}
