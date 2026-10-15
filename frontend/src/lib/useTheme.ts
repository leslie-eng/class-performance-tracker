import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

const KEY = 'classtrack.theme'

function stored(): Theme | null {
    try {
        const v = localStorage.getItem(KEY)
        return v === 'dark' || v === 'light' ? v : null
    } catch {
        return null // storage blocked (private mode); fall back to the system preference
    }
}

function preferred(): Theme {
    return stored() ?? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
}

/**
 * Reads and writes the theme.
 *
 * The class is also set by an inline script in index.html before first paint, so a
 * dark-mode visitor never sees a white flash; this hook just keeps it in sync after that.
 */
export function useTheme() {
    const [theme, setThemeState] = useState<Theme>(preferred)

    useEffect(() => {
        document.documentElement.classList.toggle('dark', theme === 'dark')
    }, [theme])

    const setTheme = useCallback((next: Theme) => {
        setThemeState(next)
        try {
            localStorage.setItem(KEY, next)
        } catch {
            /* the class still applies for this session */
        }
    }, [])

    const toggle = useCallback(() => setTheme(theme === 'dark' ? 'light' : 'dark'), [theme, setTheme])

    return { theme, setTheme, toggle }
}
