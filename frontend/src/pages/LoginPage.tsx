import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookOpen, Lock } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { Button, Spinner } from '../components/ui'

export default function LoginPage() {
  const { login, isLoading } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await login(username, password)
      navigate('/', { replace: true })
    } catch {
      setError('Invalid credentials. Please check your username and password.')
    }
  }

  return (
    <div className="min-h-screen bg-corp-light flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
          {/* Header stripe */}
          <div className="bg-corp-navy px-8 py-8 text-white text-center">
            <div className="flex justify-center mb-3">
              <div className="bg-white/10 rounded-full p-3">
                <BookOpen className="w-8 h-8" />
              </div>
            </div>
            <h1 className="text-2xl font-bold tracking-tight">Corp Library</h1>
            <p className="mt-1 text-blue-200 text-sm">Shared documents &amp; resources</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="px-8 py-8 space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Corporate username
              </label>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                placeholder="john.doe"
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 text-sm
                           focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                           placeholder-gray-400"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Password
              </label>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 text-sm
                           focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                           placeholder-gray-400"
              />
            </div>

            {error && (
              <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg">
                <Lock className="w-4 h-4 flex-shrink-0 mt-0.5" />
                {error}
              </div>
            )}

            <Button type="submit" className="w-full justify-center py-2.5" disabled={isLoading}>
              {isLoading ? <Spinner className="w-4 h-4" /> : 'Sign in with corporate account'}
            </Button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-gray-400">
          Use your Active Directory credentials · Contact IT for access issues
        </p>
      </div>
    </div>
  )
}
