import { useEffect, useSyncExternalStore } from 'react'

function prefersReducedMotion(): boolean {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/**
 * Counts from 0 up to `value` once, for stat numbers that deserve a little life.
 *
 * The animation frame writes into a module-level store that the hook subscribes to with
 * useSyncExternalStore, rather than setState inside an effect — the latter tripped oxlint's
 * set-state-in-effect rule everywhere else in this codebase, so it is avoided here too.
 * The effect only starts the tween; it never sets React state directly.
 *
 * Under `prefers-reduced-motion`, no tween runs at all and the final value is returned.
 */
let current = 0
const listeners = new Set<() => void>()

function emit() {
    for (const listener of listeners) listener()
}
function subscribe(onChange: () => void): () => void {
    listeners.add(onChange)
    return () => {
        listeners.delete(onChange)
    }
}
const getSnapshot = () => current

export function useCountUp(value: number, durationMs = 700): number {
    useEffect(() => {
        if (prefersReducedMotion() || value === 0) {
            current = value
            emit()
            return
        }
        let frame = 0
        const start = performance.now()
        const tick = (now: number) => {
            const t = Math.min(1, (now - start) / durationMs)
            const eased = 1 - Math.pow(1 - t, 3) // ease-out cubic
            current = Math.round(value * eased)
            emit()
            if (t < 1) frame = requestAnimationFrame(tick)
        }
        frame = requestAnimationFrame(tick)
        return () => cancelAnimationFrame(frame)
    }, [value, durationMs])

    // useSyncExternalStore re-renders on every emit, so the number ticks up.
    return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}
