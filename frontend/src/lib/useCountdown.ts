import { useEffect, useState } from 'react'
import { secondsToMidnight } from './dates'

/** Live seconds until midnight in `timezone`. */
export function useCountdown(timezone: string | undefined) {
  const [secs, setSecs] = useState(() => (timezone ? secondsToMidnight(timezone) : 0))
  useEffect(() => {
    if (!timezone) return
    const tick = () => setSecs(secondsToMidnight(timezone))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [timezone])
  return secs
}
