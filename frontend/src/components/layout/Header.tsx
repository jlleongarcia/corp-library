import { NavLink, useNavigate } from 'react-router-dom'
import { BookOpen, FolderTree, LogOut, Map, Search, ShieldCheck } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import { cn } from '../../lib/utils'

function NavItem({ to, icon, label, end }: { to: string; icon: React.ReactNode; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => cn(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
        isActive ? 'bg-white/15 text-white' : 'text-blue-100 hover:bg-white/10 hover:text-white',
      )}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </NavLink>
  )
}

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
          <span className="hidden md:inline">Corp Library</span>
        </button>

        <nav className="flex items-center gap-1">
          <NavItem to="/" end icon={<Search className="w-4 h-4" />} label="Search" />
          <NavItem to="/browse" icon={<FolderTree className="w-4 h-4" />} label="Browse" />
          <NavItem to="/guide" icon={<Map className="w-4 h-4" />} label="Folder guide" />
          {user?.is_admin && <NavItem to="/admin" icon={<ShieldCheck className="w-4 h-4" />} label="Admin" />}
        </nav>

        <div className="ml-auto flex items-center gap-3 flex-shrink-0">
          <div className="text-sm text-right hidden md:block">
            <p className="font-semibold leading-none">{user?.display_name ?? user?.username}</p>
            <p className="text-gray-300 text-xs mt-0.5">{user?.email ?? ''}</p>
          </div>
          <button
            onClick={() => logout().then(() => navigate('/login'))}
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
