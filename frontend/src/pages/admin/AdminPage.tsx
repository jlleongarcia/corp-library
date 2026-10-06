import { Navigate, NavLink, useParams } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { cn } from '../../lib/utils'
import OverviewTab from './OverviewTab'
import SharesTab from './SharesTab'
import ActivityTab from './ActivityTab'
import DuplicatesTab from './DuplicatesTab'
import StaleTab from './StaleTab'
import HygieneTab from './HygieneTab'
import PermissionsTab from './PermissionsTab'

const TABS = [
  { id: 'overview', label: 'Overview', element: <OverviewTab /> },
  { id: 'shares', label: 'Shares', element: <SharesTab /> },
  { id: 'activity', label: 'Scan activity', element: <ActivityTab /> },
  { id: 'permissions', label: 'Permissions', element: <PermissionsTab /> },
  { id: 'duplicates', label: 'Duplicates', element: <DuplicatesTab /> },
  { id: 'stale', label: 'Stale files', element: <StaleTab /> },
  { id: 'hygiene', label: 'Hygiene', element: <HygieneTab /> },
]

export default function AdminPage() {
  const { user } = useAuth()
  const { tab = 'overview' } = useParams()
  if (!user?.is_admin) return <Navigate to="/" replace />
  const current = TABS.find((t) => t.id === tab)
  if (!current) return <Navigate to="/admin" replace />

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Admin console</h1>
        <p className="text-sm text-gray-500">Inventory and permission reports for the department shares.</p>
      </div>
      <nav className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-gray-200">
        {TABS.map((t) => (
          <NavLink
            key={t.id}
            to={t.id === 'overview' ? '/admin' : `/admin/${t.id}`}
            end
            className={cn(
              'px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors',
              t.id === current.id
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-gray-500 hover:text-gray-800',
            )}
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      {current.element}
    </div>
  )
}
