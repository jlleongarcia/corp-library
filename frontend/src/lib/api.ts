import axios from 'axios'

// The session lives in an HttpOnly cookie the browser sends by itself; this code
// never sees it. Every request carries X-Requested-With, which the API requires
// on changes as CSRF protection (other sites can't add that header).
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  timeout: 30_000,
  headers: { 'X-Requested-With': 'XMLHttpRequest' },
})

/** Called when a request finds the session gone (expired, signed out elsewhere, removed from AD). */
let onSessionLost: () => void = () => {}
export function setSessionLostHandler(handler: () => void) {
  onSessionLost = handler
}

api.interceptors.response.use(
  (res) => res,
  (err) => {
    // 401s from /auth/* are answers about signing in (wrong password, SSO not
    // possible): the sign-in page handles them.
    const isAuthCall = String(err.config?.url ?? '').startsWith('/auth/')
    if (err.response?.status === 401 && !isAuthCall) onSessionLost()
    return Promise.reject(err)
  },
)

/** The message the API put in `detail`, or a fallback. */
export function errorMessage(err: unknown, fallback = 'Something went wrong'): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : (err as Error)?.message ?? fallback
}

/** Where the browser downloads a file from: a plain link works, the cookie goes with it. */
export function apiUrl(path: string): string {
  return `${api.defaults.baseURL}${path}`
}

export default api
