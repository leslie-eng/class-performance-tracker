import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { RequestErrorToast, reportQueryError } from './components/RequestErrorToast'
import { ApiError } from './lib/api'
import { SessionProvider } from './lib/session'
import './index.css'

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: reportQueryError }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Retry network errors (status 0) and 5xx; a 4xx won't change on retry.
      retry: (count, err) => !(err instanceof ApiError && err.status > 0 && err.status < 500) && count < 2,
      refetchOnWindowFocus: true,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>
      <RequestErrorToast />
    </QueryClientProvider>
  </StrictMode>,
)
