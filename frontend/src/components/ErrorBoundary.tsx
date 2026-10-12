import { Component, createRef, type ErrorInfo, type ReactNode } from 'react'

interface Props {
    children: ReactNode
    /** Optional custom fallback. Receives the error and a reset callback. */
    fallback?: (error: Error, reset: () => void) => ReactNode
}

interface State {
    error: Error | null
}

/**
 * Catches render/lifecycle errors so one broken page can't blank the whole app.
 *
 * The fallback is intentionally self-contained (no imports from ./ui or the session/query
 * providers): if those are what threw, a fallback that depends on them would throw too and the
 * user would still get a white screen.
 */
export class ErrorBoundary extends Component<Props, State> {
    state: State = { error: null }
    private readonly headingRef = createRef<HTMLHeadingElement>()

    static getDerivedStateFromError(error: Error): State {
        return { error }
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        // Hook a reporter (Sentry, etc.) in here. componentStack is dev-only detail.
        console.error('[error-boundary] uncaught render error', error, info.componentStack)
        // Move focus to the fallback heading so keyboard and screen-reader users are told
        // the app left its normal state instead of silently landing on a dead page.
        this.headingRef.current?.focus()
    }

    private readonly reset = () => this.setState({ error: null })

    render() {
        const { error } = this.state
        if (!error) return this.props.children
        if (this.props.fallback) return this.props.fallback(error, this.reset)

        return (
            <div className="flex min-h-screen items-center justify-center bg-surface px-4 py-10">
                <div role="alert" className="w-full max-w-lg rounded-2xl bg-white p-6 text-center shadow-modal">
                    <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-error-container text-error">
                        <span aria-hidden className="material-symbols-outlined text-[28px]">
                            error
                        </span>
                    </span>
                    <h1
                        ref={this.headingRef}
                        tabIndex={-1}
                        className="mt-4 text-headline-md text-ink outline-none"
                    >
                        Something went wrong
                    </h1>
                    <p className="mt-2 text-body-md text-on-surface-variant">
                        This part of ClassTrack hit an unexpected error. Your submissions are saved on the
                        server, so reloading usually fixes it.
                    </p>
                    <pre className="mt-3 max-h-24 overflow-auto rounded-lg bg-surface-container-low px-3 py-2 text-left font-mono text-label-sm break-words whitespace-pre-wrap text-on-surface-variant">
                        {error.message || String(error)}
                    </pre>
                    <div className="mt-5 flex flex-wrap justify-center gap-2">
                        <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
                            Reload page
                        </button>
                        <button type="button" className="btn-secondary" onClick={this.reset}>
                            Try again
                        </button>
                        <a href="/" className="btn-secondary">
                            Back to dashboard
                        </a>
                    </div>
                </div>
            </div>
        )
    }
}
