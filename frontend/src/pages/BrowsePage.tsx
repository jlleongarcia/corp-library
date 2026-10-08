import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, EyeOff, Folder, HardDrive } from 'lucide-react'
import api from '../lib/api'
import type { BrowseResponse, BrowseShare } from '../types'
import { formatDate, formatFileSize } from '../lib/utils'
import { EmptyState } from '../components/ui'
import { CopyPathButton, FileTypeBadge } from '../components/library'
import { ErrorNote, Loading } from './admin/common'

export default function BrowsePage() {
  const { folderId } = useParams()
  return folderId ? <FolderView folderId={Number(folderId)} /> : <ShareList />
}

function ShareList() {
  const shares = useQuery<BrowseShare[]>({
    queryKey: ['browse-shares'],
    queryFn: () => api.get('/browse/shares').then((r) => r.data),
  })
  if (shares.isLoading) return <Loading />
  if (shares.error) return <ErrorNote error={shares.error} />
  if (!shares.data?.length) {
    return (
      <EmptyState
        icon={<HardDrive className="w-12 h-12" />}
        title="No shares to browse"
        description="None of the indexed shares can be opened with your account. Search may still find documents in folders you have access to."
      />
    )
  }
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Browse</h1>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {shares.data.map((s) => (
          <li key={s.id}>
            <Link to={`/browse/${s.root_folder_id}`}
                  className="flex items-center gap-3 bg-white rounded-xl border border-gray-200 shadow-sm p-4 hover:border-blue-300">
              <HardDrive className="w-8 h-8 text-blue-600 flex-shrink-0" />
              <span className="min-w-0">
                <span className="block font-semibold text-gray-900">{s.name}</span>
                <span className="block text-xs text-gray-500 font-mono truncate">{s.path}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

function FolderView({ folderId }: { folderId: number }) {
  const view = useQuery<BrowseResponse>({
    queryKey: ['browse', folderId],
    queryFn: () => api.get(`/browse/folders/${folderId}`).then((r) => r.data),
  })
  if (view.isLoading) return <Loading />
  if (view.error) return <ErrorNote error={view.error} />
  const v = view.data!

  return (
    <div className="space-y-4">
      <nav className="flex flex-wrap items-center gap-1 text-sm" aria-label="Breadcrumb">
        <Link to="/browse" className="text-blue-700 hover:underline">Shares</Link>
        {v.breadcrumbs.map((b, i) => (
          <span key={i} className="flex items-center gap-1">
            <ChevronRight className="w-4 h-4 text-gray-400" />
            {b.folder_id && i < v.breadcrumbs.length - 1
              ? <Link to={`/browse/${b.folder_id}`} className="text-blue-700 hover:underline">{b.name}</Link>
              : <span className={i === v.breadcrumbs.length - 1 ? 'font-semibold text-gray-900' : 'text-gray-500'}>{b.name}</span>}
          </span>
        ))}
      </nav>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-xs text-gray-500 break-all">{v.folder.path}</p>
        <CopyPathButton path={v.folder.path} label="Copy folder path" />
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm divide-y divide-gray-100">
        {v.folders.map((f) => (
          <Link key={f.id} to={`/browse/${f.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50">
            <Folder className="w-5 h-5 text-amber-500 flex-shrink-0" />
            <span className="flex-1 text-sm font-medium text-gray-900 break-all">{f.name}</span>
            <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(f.mtime)}</span>
          </Link>
        ))}
        {v.files.map((f) => (
          <Link key={f.file_id} to={`/documents/${f.file_id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50">
            <FileTypeBadge ext={f.extension} />
            <span className="flex-1 text-sm text-gray-900 break-all">{f.name}</span>
            <span className="text-xs text-gray-500 tabular-nums whitespace-nowrap w-20 text-right">{formatFileSize(f.size)}</span>
            <span className="text-xs text-gray-500 whitespace-nowrap w-24 text-right">{formatDate(f.mtime)}</span>
          </Link>
        ))}
        {v.files_hidden && (
          <p className="flex items-center gap-2 px-4 py-3 text-sm text-gray-500">
            <EyeOff className="w-4 h-4" /> You can see this folder, but not open the files in it.
          </p>
        )}
        {v.files_truncated && (
          <p className="px-4 py-3 text-sm text-gray-500">Only the first 1,000 files are listed. Use search to find the others.</p>
        )}
        {!v.folders.length && !v.files.length && !v.files_hidden && (
          <p className="px-4 py-6 text-sm text-gray-500 text-center">This folder is empty.</p>
        )}
      </div>
    </div>
  )
}
