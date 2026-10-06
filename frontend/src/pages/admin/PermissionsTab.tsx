import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Lock } from 'lucide-react'
import api from '../../lib/api'
import type { AccessLevel, AclException, PermissionGrid } from '../../types'
import { Badge } from '../../components/ui'
import { cn } from '../../lib/utils'
import { Card, ErrorNote, ExportButton, Loading, PathText } from './common'

const LEVEL_STYLE: Record<AccessLevel, string> = {
  full: 'bg-purple-100 text-purple-800',
  modify: 'bg-blue-100 text-blue-800',
  write: 'bg-amber-100 text-amber-800',
  read: 'bg-green-100 text-green-800',
  none: 'text-gray-300',
}

function Level({ level }: { level: AccessLevel }) {
  return (
    <span className={cn('inline-block min-w-[3.5rem] text-center rounded px-1.5 py-0.5 text-xs font-medium', LEVEL_STYLE[level])}>
      {level === 'none' ? '—' : level}
    </span>
  )
}

function lastSegment(path: string) {
  const parts = path.split('\\').filter(Boolean)
  return parts[parts.length - 1] ?? path
}

export default function PermissionsTab() {
  const grid = useQuery<PermissionGrid>({
    queryKey: ['reports', 'permissions'],
    queryFn: () => api.get('/admin/reports/permissions').then((r) => r.data),
  })
  const exceptions = useQuery<AclException[]>({
    queryKey: ['reports', 'acl-exceptions'],
    queryFn: () => api.get('/admin/reports/acl-exceptions').then((r) => r.data),
  })

  return (
    <div className="space-y-6">
      <Card title="Who can access what" actions={<ExportButton path="/admin/reports/permissions" />}>
        <p className="text-sm text-gray-500 mb-4">
          Effective access per user, computed from the folders' Windows permissions and AD group membership.
          Columns are share roots and folders where permissions were changed. Hover a column for its full path.
        </p>
        {grid.isLoading ? <Loading /> : grid.error || !grid.data ? <ErrorNote error={grid.error} /> : (
          grid.data.columns.length === 0 ? <p className="text-sm text-gray-500 text-center py-4">No permissions recorded yet. Run a scan first.</p> : (
            <div className="overflow-x-auto -mx-5">
              <table className="text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="sticky left-0 bg-white px-5 py-2 text-left text-xs uppercase tracking-wide text-gray-500 font-medium">User</th>
                    {grid.data.columns.map((c) => (
                      <th key={c.folder_id} title={c.path} className="px-2 py-2 text-xs font-medium text-gray-600 whitespace-nowrap">
                        {lastSegment(c.path)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {grid.data.rows.map((r) => (
                    <tr key={r.sid ?? r.name} className={cn('hover:bg-gray-50', r.kind === 'everyone' && 'bg-amber-50/40')}>
                      <td className="sticky left-0 bg-white px-5 py-1.5 whitespace-nowrap">
                        <span className="font-medium">{r.display_name ?? r.name}</span>
                        {r.kind === 'unknown' && <Badge variant="red" className="ml-2">unresolved</Badge>}
                        {r.display_name && r.kind === 'user' && <span className="ml-2 text-xs text-gray-500">{r.name}</span>}
                      </td>
                      {grid.data.columns.map((c) => (
                        <td key={c.folder_id} className="px-2 py-1.5 text-center"><Level level={r.cells[c.folder_id]} /></td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </Card>

      <Card title="Permission exceptions" actions={<ExportButton path="/admin/reports/acl-exceptions" />}>
        <p className="text-sm text-gray-500 mb-4">
          Folders whose permissions differ from their parent: set explicitly, inheritance disabled, or unreadable
          by the scanner. Unresolved accounts are usually local groups on the file server or deleted users.
        </p>
        {exceptions.isLoading ? <Loading /> : exceptions.error || !exceptions.data ? <ErrorNote error={exceptions.error} /> : (
          <ul className="divide-y divide-gray-100">
            {exceptions.data.map((f) => (
              <li key={f.folder_id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <PathText path={f.path} />
                  {f.is_share_root && <Badge variant="gray">share root</Badge>}
                  {f.inheritance_disabled && <Badge variant="blue"><Lock className="w-3 h-3 mr-1" />inheritance off</Badge>}
                  {f.null_dacl && <Badge variant="red">no ACL: everyone has full access</Badge>}
                  {f.acl_error && <Badge variant="red"><AlertTriangle className="w-3 h-3 mr-1" />{f.acl_error}</Badge>}
                </div>
                {f.entries.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {f.entries.filter((e) => !e.inherited).map((e, i) => (
                      <li key={i} className={cn('flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs',
                        e.type === 'deny' ? 'border-red-200 bg-red-50' : 'border-gray-200')}>
                        {e.type === 'deny' && <span className="font-semibold text-red-700">DENY</span>}
                        <span className={cn(e.kind === 'unknown' && 'font-mono text-red-700')}>{e.display_name ?? e.name}</span>
                        <Level level={e.level} />
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
