import { Outlet, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { Spinner } from '../ui'
import Header from './Header'
import { PrivacyFooter } from '../privacy'

export default function AppLayout() {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') {
    return <div className="min-h-screen flex items-center justify-center"><Spinner /></div>
  }
  if (status === 'signed-out') {
    // Come back to the same page (e.g. a shared document link) after signing in.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />
      <main className="flex-1 w-full max-w-screen-xl mx-auto p-4 md:p-6">
        <Outlet />
      </main>
      <PrivacyFooter className="w-full max-w-screen-xl mx-auto px-4 md:px-6 pb-6 pt-2 border-t border-gray-200" />
    </div>
  )
}
