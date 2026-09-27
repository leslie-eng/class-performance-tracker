import { Link, useNavigate } from 'react-router-dom'
import { EmptyState, ErrorBanner, Icon, PageLoader } from '../components/ui'
import { useChallenges, useEnroll } from '../lib/queries'
import { useSession } from '../lib/session'

export default function JoinPage() {
  const { user, meta, challenges: mine, selectChallenge } = useSession()
  const all = useChallenges()
  const enroll = useEnroll()
  const navigate = useNavigate()

  if (all.isLoading || !meta) return <PageLoader />
  const today = meta.today
  const mineIds = new Set(mine.map((c) => c.id))
  const list = (all.data ?? []).filter((c) => c.end_date >= today || mineIds.has(c.id))

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-headline-lg text-ink md:text-[28px]">{mine.length ? 'Your challenges' : 'Join a challenge'}</h1>
        <p className="text-body-md text-on-surface-variant">
          Pick a challenge to start logging daily tasks. You can be in more than one at a time.
        </p>
      </div>
      <ErrorBanner error={enroll.error} />
      {list.length === 0 ? (
        <div className="card">
          <EmptyState icon="flag" title="No open challenges yet">
            {user?.is_admin ? (
              <>
                Create the first one from the <Link to="/admin" className="text-primary-container underline">admin page</Link>.
              </>
            ) : (
              'Ask your group admin to create a challenge, then come back here to join.'
            )}
          </EmptyState>
        </div>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {list.map((c) => {
            const joined = mineIds.has(c.id)
            const state = c.start_date > today ? 'Starts ' + c.start_date : c.end_date < today ? 'Ended' : 'Active now'
            return (
              <li key={c.id} className="card flex flex-col gap-3 p-6">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-headline-md text-ink">{c.name}</h2>
                  <span className={`pill shrink-0 ${state === 'Active now' ? 'bg-secondary-container text-on-secondary-container' : 'bg-surface-container text-on-surface-variant'}`}>{state}</span>
                </div>
                {c.description && <p className="text-body-md text-on-surface-variant">{c.description}</p>}
                <p className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-label-sm text-on-surface-variant">
                  <span>
                    <Icon name="calendar_today" className="text-[14px]" /> {c.total_days} days
                  </span>
                  <span>
                    <Icon name="task" className="text-[14px]" /> {c.task_types_allowed === 'both' ? 'code + articles' : c.task_types_allowed}
                  </span>
                </p>
                <div className="mt-auto pt-2">
                  {joined ? (
                    <button
                      className="btn-secondary w-full"
                      onClick={() => {
                        selectChallenge(c.id)
                        navigate('/')
                      }}
                    >
                      <Icon name="check" className="text-[18px] text-secondary" /> Joined · open dashboard
                    </button>
                  ) : (
                    <button
                      className="btn-primary w-full"
                      disabled={enroll.isPending}
                      onClick={() =>
                        enroll.mutate(c.id, {
                          onSuccess: () => {
                            selectChallenge(c.id)
                            navigate('/')
                          },
                        })
                      }
                    >
                      Join challenge
                    </button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
