import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  BarChart3, FolderCog, Play, Plus, RefreshCw, Shield, Trash2, Edit2, X, Check, AlertCircle,
} from 'lucide-react'
import api from '../lib/api'
import type { ScanConfig, SystemStats } from '../types'
import { Button, Spinner, Badge } from '../components/ui'
import { formatDate } from '../lib/utils'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

// ── Scan status badge ──────────────────────────────────────────────────────────
function ScanStatusBadge({ status }: { status: string }) {
  const map: Record<string, { variant: 'default' | 'green' | 'red' | 'gray'; label: string }> = {
    never:   { variant: 'gray',    label: 'Never run' },
    running: { variant: 'default', label: 'Running…'  },
    success: { variant: 'green',   label: 'OK'        },
    error:   { variant: 'red',     label: 'Error'     },
  }
  const { variant, label } = map[status] ?? { variant: 'gray', label: status }
  return <Badge variant={variant}>{label}</Badge>
}

// ── Scan config form modal ─────────────────────────────────────────────────────
interface ConfigFormProps {
  initial?: ScanConfig
  onClose: () => void
  onSave: (data: Omit<ScanConfig, 'id' | 'last_scan' | 'scan_status' | 'scan_error' | 'documents_found' | 'created_at'>) => void
  isSaving: boolean
}

function ConfigForm({ initial, onClose, onSave, isSaving }: ConfigFormProps) {
  const [name, setName] = useState(initial?.name ?? '')
  const [path, setPath] = useState(initial?.root_path ?? '')
  const [groups, setGroups] = useState(initial?.allowed_groups.join(', ') ?? '')
  const [depth, setDepth] = useState(initial?.max_depth ?? 5)
  const [active, setActive] = useState(initial?.is_active ?? true)
  const [subCats, setSubCats] = useState(initial?.create_subcategories ?? true)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onSave({
      name,
      root_path: path,
      root_category_id: initial?.root_category_id ?? null,
      allowed_groups: groups.split(',').map((g) => g.trim()).filter(Boolean),
      max_depth: depth,
      file_extensions: initial?.file_extensions ?? null,
      is_active: active,
      create_subcategories: subCats,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-bold text-gray-900">{initial ? 'Edit scan config' : 'New scan config'}</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 transition-colors">
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Name *</span>
            <input
              required value={name} onChange={(e) => setName(e.target.value)}
              placeholder="e.g. HR Documents"
              className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Network path (UNC) *</span>
            <input
              required value={path} onChange={(e) => setPath(e.target.value)}
              placeholder="\\server\share\hr"
              className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">
              Allowed AD groups <span className="font-normal text-gray-400">(comma-separated, leave empty = public)</span>
            </span>
            <input
              value={groups} onChange={(e) => setGroups(e.target.value)}
              placeholder="HR_Staff, HR_Managers, IT_Admins"
              className="mt-1 w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Max folder depth</span>
            <input
              type="number" min={1} max={10} value={depth}
              onChange={(e) => setDepth(parseInt(e.target.value, 10))}
              className="mt-1 w-24 px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <div className="flex gap-6">
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded" />
              Active
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input type="checkbox" checked={subCats} onChange={(e) => setSubCats(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded" />
              Create sub-categories from sub-folders
            </label>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" type="button" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving ? <Spinner className="w-4 h-4" /> : <Check className="w-4 h-4" />}
              Save
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
type Tab = 'overview' | 'scans'

export default function AdminPage() {
  const { user } = useAuth()
  if (!user?.is_admin) return <Navigate to="/" replace />

  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('overview')
  const [editingConfig, setEditingConfig] = useState<ScanConfig | null | 'new'>(null)

  const { data: stats } = useQuery<SystemStats>({
    queryKey: ['admin', 'stats'],
    queryFn: () => api.get('/admin/stats').then((r) => r.data),
    refetchInterval: 15_000,
  })

  const { data: configs = [], isLoading: loadingConfigs } = useQuery<ScanConfig[]>({
    queryKey: ['admin', 'scan-configs'],
    queryFn: () => api.get('/admin/scan-configs').then((r) => r.data),
    refetchInterval: 10_000,
  })

  const createMutation = useMutation({
    mutationFn: (data: object) => api.post('/admin/scan-configs', data).then((r) => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin'] }); setEditingConfig(null) },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: object }) =>
      api.put(`/admin/scan-configs/${id}`, data).then((r) => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin'] }); setEditingConfig(null) },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/scan-configs/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin'] }),
  })

  const triggerMutation = useMutation({
    mutationFn: (id: number) => api.post(`/admin/scan-configs/${id}/trigger`),
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['admin'] }), 2000),
  })

  const rebuildMutation = useMutation({
    mutationFn: () => api.post('/admin/rebuild-index'),
  })

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleSave(data: any) {
    if (editingConfig === 'new') {
      createMutation.mutate(data)
    } else if (editingConfig) {
      updateMutation.mutate({ id: editingConfig.id, data })
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Shield className="w-6 h-6 text-blue-600" />
        <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {([['overview', 'Overview', <BarChart3 className="w-4 h-4" />], ['scans', 'Scan Configs', <FolderCog className="w-4 h-4" />]] as const).map(
          ([key, label, icon]) => (
            <button
              key={key}
              onClick={() => setTab(key as Tab)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === key ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {icon}
              {label}
            </button>
          ),
        )}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Documents', value: stats?.total_documents, color: 'text-blue-600', bg: 'bg-blue-50' },
              { label: 'Categories', value: stats?.total_categories, color: 'text-green-600', bg: 'bg-green-50' },
              { label: 'Scan configs', value: stats?.total_scan_configs, color: 'text-purple-600', bg: 'bg-purple-50' },
              { label: 'Users', value: stats?.total_users, color: 'text-orange-600', bg: 'bg-orange-50' },
            ].map((s) => (
              <div key={s.label} className={`${s.bg} rounded-xl p-5`}>
                <p className="text-xs text-gray-500 font-medium mb-1">{s.label}</p>
                <p className={`text-3xl font-bold ${s.color}`}>{s.value ?? '—'}</p>
              </div>
            ))}
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold text-gray-800 mb-1">Search Index</h3>
            <p className="text-sm text-gray-500 mb-4">
              The FTS5 index is rebuilt automatically after every scan. Use the button below if
              search results look stale or incomplete.
            </p>
            <Button
              onClick={() => rebuildMutation.mutate()}
              disabled={rebuildMutation.isPending}
              variant="secondary"
            >
              {rebuildMutation.isPending
                ? <Spinner className="w-4 h-4" />
                : <RefreshCw className="w-4 h-4" />}
              Rebuild search index
            </Button>
            {rebuildMutation.isSuccess && (
              <p className="mt-2 text-xs text-green-600 flex items-center gap-1">
                <Check className="w-3 h-3" /> Index rebuild started.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Scan configs tab */}
      {tab === 'scans' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500">
              Configure which network paths to index and which AD groups have access.
            </p>
            <Button onClick={() => setEditingConfig('new')}>
              <Plus className="w-4 h-4" /> Add scan config
            </Button>
          </div>

          {loadingConfigs && <div className="flex justify-center py-10"><Spinner /></div>}

          {!loadingConfigs && configs.length === 0 && (
            <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center">
              <FolderCog className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">No scan configs yet</p>
              <p className="text-xs text-gray-400 mt-1">Add a config to start indexing network folders.</p>
            </div>
          )}

          {configs.map((cfg) => (
            <div key={cfg.id} className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold text-gray-900">{cfg.name}</h3>
                    <ScanStatusBadge status={cfg.scan_status} />
                    {!cfg.is_active && <Badge variant="gray">Inactive</Badge>}
                  </div>
                  <code className="mt-1 block text-xs text-gray-500 font-mono bg-gray-50 px-2 py-1 rounded">
                    {cfg.root_path}
                  </code>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
                    <span>Depth: {cfg.max_depth}</span>
                    <span>
                      Groups:{' '}
                      {cfg.allowed_groups.length > 0 ? cfg.allowed_groups.join(', ') : 'Public'}
                    </span>
                    <span>Last scan: {formatDate(cfg.last_scan)}</span>
                    {cfg.scan_status === 'success' && (
                      <span>{cfg.documents_found} documents found</span>
                    )}
                  </div>
                  {cfg.scan_status === 'error' && cfg.scan_error && (
                    <div className="mt-2 flex items-start gap-1.5 text-xs text-red-600 bg-red-50 px-3 py-2 rounded-lg">
                      <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                      {cfg.scan_error}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Run scan now"
                    onClick={() => triggerMutation.mutate(cfg.id)}
                    disabled={cfg.scan_status === 'running' || triggerMutation.isPending}
                  >
                    <Play className="w-4 h-4" />
                  </Button>
                  <Button size="sm" variant="ghost" title="Edit" onClick={() => setEditingConfig(cfg)}>
                    <Edit2 className="w-4 h-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Delete"
                    onClick={() => {
                      if (confirm(`Delete scan config "${cfg.name}"?`)) deleteMutation.mutate(cfg.id)
                    }}
                    className="text-red-400 hover:text-red-600 hover:bg-red-50"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form modal */}
      {editingConfig !== null && (
        <ConfigForm
          initial={editingConfig === 'new' ? undefined : editingConfig}
          onClose={() => setEditingConfig(null)}
          onSave={handleSave}
          isSaving={isSaving}
        />
      )}
    </div>
  )
}
