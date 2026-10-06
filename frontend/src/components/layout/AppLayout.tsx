import { Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import Header from './Header'

export default function AppLayout() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />
      <main className="flex-1 w-full max-w-screen-xl mx-auto p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  )
}
