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
      // Only retry 5xx server errors, not client errors (4xx) or network/CORS misconfigurations (status 0).
      retry: (count, err) => err instanceof ApiError && err.status >= 500 && count < 2,
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
