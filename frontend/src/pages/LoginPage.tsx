import { type FormEvent, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { BookOpen, Lock, Monitor } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { errorMessage } from '../lib/api'
import { Button, Spinner } from '../components/ui'

const inputClass =
  'w-full px-4 py-2.5 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 ' +
  'focus:ring-blue-500 focus:border-transparent placeholder-gray-400'

export default function LoginPage() {
  const { status, config, login, loginWithSso } = useAuth()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/'
  if (status === 'signed-in') return <Navigate to={from} replace />
  if (status === 'loading') {
    return <div className="min-h-screen flex items-center justify-center"><Spinner /></div>
  }
  const devMode = config?.dev_mode ?? false

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(username, password)
    } catch (err) {
      const code = (err as { response?: { status?: number } }).response?.status
      setError(code === 401
        ? 'Invalid credentials. Please check your username and password.'
        : errorMessage(err, 'Sign-in failed. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  async function handleSso() {
    setError(null)
    setBusy(true)
    const ok = await loginWithSso()
    setBusy(false)
    if (!ok) setError("Windows sign-in isn't available on this computer. Use your username and password instead.")
  }

  return (
    <div className="min-h-screen bg-corp-light flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
          <div className="bg-corp-navy px-8 py-8 text-white text-center">
            <div className="flex justify-center mb-3">
              <div className="bg-white/10 rounded-full p-3">
                <BookOpen className="w-8 h-8" />
              </div>
            </div>
            <h1 className="text-2xl font-bold tracking-tight">{config?.app_name ?? 'Corp Library'}</h1>
            <p className="mt-1 text-blue-200 text-sm">The department's shared documents</p>
          </div>

          <div className="px-8 py-8 space-y-5">
            {config?.sso_enabled && (
              <>
                <Button type="button" className="w-full justify-center py-2.5" disabled={busy} onClick={handleSso}>
                  <Monitor className="w-4 h-4" /> Sign in with your Windows account
                </Button>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  <span className="h-px flex-1 bg-gray-200" /> or <span className="h-px flex-1 bg-gray-200" />
                </div>
              </>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              {devMode && (
                <p className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-3 py-2">
                  Development mode: sign in as any username, no password. Groups come from DEV_GROUPS.
                </p>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5" htmlFor="username">
                  Corporate username
                </label>
                <input id="username" type="text" autoComplete="username" value={username}
                       onChange={(e) => setUsername(e.target.value)} required placeholder="john.doe"
                       className={inputClass} />
              </div>
              {!devMode && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5" htmlFor="password">
                    Password
                  </label>
                  <input id="password" type="password" autoComplete="current-password" value={password}
                         onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••"
                         className={inputClass} />
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg">
                  <Lock className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  {error}
                </div>
              )}

              <Button type="submit" variant={config?.sso_enabled ? 'secondary' : 'primary'}
                      className="w-full justify-center py-2.5" disabled={busy}>
                {busy ? <Spinner className="w-4 h-4" /> : 'Sign in with username and password'}
              </Button>
            </form>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-gray-400">
          Use your Windows (Active Directory) account · Contact IT for access issues
        </p>
      </div>
    </div>
  )
}
