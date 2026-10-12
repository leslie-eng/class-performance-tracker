import { useEffect, useState } from 'react'

function secondsLeft(deadline: string | undefined, offsetMs: number) {
  if (!deadline) return 0
  return Math.max(0, Math.ceil((new Date(deadline).getTime() - (Date.now() + offsetMs)) / 1000))
}

/**
 * Live seconds until `deadline` (ISO), measured on the server's clock: `serverNow` is the
 * server time when the data was fetched, so a wrong device clock can't add or steal time.
 */
export function useDeadline(deadline: string | undefined, serverNow: string | undefined) {
  const [offset] = useState(() => (serverNow ? new Date(serverNow).getTime() - Date.now() : 0))
  const [secs, setSecs] = useState(() => secondsLeft(deadline, offset))
  useEffect(() => {
    if (!deadline) return
    const tick = () => setSecs(secondsLeft(deadline, offset))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [deadline, offset])
  return secs
}
