import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'
import api, { setSessionLostHandler } from '../lib/api'
import type { AuthConfig, User } from '../types'

type Status = 'loading' | 'signed-in' | 'signed-out'

interface AuthContextValue {
  user: User | null
  status: Status
  config: AuthConfig | null
  login: (username: string, password: string) => Promise<void>
  /** Try Kerberos single sign-on; resolves to whether it worked. */
  loginWithSso: () => Promise<boolean>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

// After signing out, don't sign straight back in with SSO on the next page load.
const SIGNED_OUT_KEY = 'corplib.signedOut'

function signedOutByUser(): boolean {
  try {
    return sessionStorage.getItem(SIGNED_OUT_KEY) === '1'
  } catch {
    return false
  }
}

function rememberSignedOut(value: boolean) {
  try {
    if (value) sessionStorage.setItem(SIGNED_OUT_KEY, '1')
    else sessionStorage.removeItem(SIGNED_OUT_KEY)
  } catch {
    /* storage unavailable: SSO will simply be retried */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const queryClient = useQueryClient()

  const signedIn = useCallback((u: User) => {
    rememberSignedOut(false)
    setUser(u)
    setStatus('signed-in')
  }, [])

  const signedOut = useCallback(() => {
    setUser(null)
    setStatus('signed-out')
    queryClient.clear() // nothing of the previous user's results may linger
  }, [queryClient])

  const loginWithSso = useCallback(async () => {
    try {
      // The browser answers the Negotiate challenge with a Kerberos ticket by itself.
      const { data } = await api.get<User>('/auth/sso')
      signedIn(data)
      return true
    } catch {
      return false
    }
  }, [signedIn])

  // On load: an existing session, else SSO, else the sign-in page.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const cfg = await api.get<AuthConfig>('/auth/config').then((r) => r.data).catch(() => null)
      if (cancelled) return
      setConfig(cfg)
      try {
        const { data } = await api.get<User>('/auth/me')
        if (!cancelled) signedIn(data)
        return
      } catch {
        /* not signed in */
      }
      if (cfg?.sso_enabled && !signedOutByUser() && (await loginWithSso())) return
      if (!cancelled) setStatus('signed-out')
    })()
    return () => {
      cancelled = true
    }
  }, [signedIn, loginWithSso])

  useEffect(() => setSessionLostHandler(signedOut), [signedOut])

  const login = useCallback(async (username: string, password: string) => {
    const { data } = await api.post<User>('/auth/login', { username, password })
    signedIn(data)
  }, [signedIn])

  const logout = useCallback(async () => {
    rememberSignedOut(true)
    await api.post('/auth/logout').catch(() => undefined)
    signedOut()
  }, [signedOut])

  return (
    <AuthContext.Provider value={{ user, status, config, login, loginWithSso, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
