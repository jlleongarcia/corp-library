import { useNavigate } from 'react-router-dom'
import { LogOut, ShieldCheck, BookOpen } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'

export default function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <header className="bg-corp-navy text-white shadow-md z-20 flex-shrink-0">
      <div className="max-w-screen-xl mx-auto px-4 h-16 flex items-center gap-4">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 font-bold text-lg tracking-tight hover:text-blue-200 transition-colors flex-shrink-0"
        >
          <BookOpen className="w-6 h-6" />
          <span className="hidden sm:inline">Corp Library</span>
        </button>

        <div className="ml-auto flex items-center gap-3 flex-shrink-0">
          {user?.is_admin && (
            <button
              onClick={() => navigate('/admin')}
              title="Admin console"
              className="flex items-center gap-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-500
                         px-3 py-1.5 rounded-lg transition-colors"
            >
              <ShieldCheck className="w-4 h-4" />
              <span className="hidden sm:inline">Admin</span>
            </button>
          )}
          <div className="text-sm text-right hidden md:block">
            <p className="font-semibold leading-none">{user?.display_name ?? user?.username}</p>
            <p className="text-gray-300 text-xs mt-0.5">{user?.email ?? ''}</p>
          </div>
          <button
            onClick={logout}
            title="Sign out"
            className="p-2 rounded-lg hover:bg-white/10 transition-colors"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </div>
    </header>
  )
}
