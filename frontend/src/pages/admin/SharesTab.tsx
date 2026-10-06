import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Edit2, Play, Plus, Trash2, X } from 'lucide-react'
import api from '../../lib/api'
import type { Share } from '../../types'
import { Badge, Button } from '../../components/ui'
import { Card, ErrorNote, Loading, Table } from './common'

type Draft = { name: string; path: string; enabled: boolean }

function ShareForm({ initial, onCancel, onSave, saving }: {
  initial?: Share; onCancel: () => void; onSave: (d: Draft) => void; saving: boolean
}) {
  const [draft, setDraft] = useState<Draft>({
    name: initial?.name ?? '', path: initial?.path ?? '', enabled: initial?.enabled ?? true,
  })
  const input = 'w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
  return (
    <form
      onSubmit={(e: FormEvent) => { e.preventDefault(); onSave(draft) }}
      className="grid gap-3 md:grid-cols-[1fr_2fr_auto_auto] items-end bg-gray-50 rounded-lg p-4"
    >
      <label className="block">
        <span className="text-xs font-medium text-gray-600">Name</span>
        <input required className={input} value={draft.name} placeholder="Finance"
          onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </label>
      <label className="block">
        <span className="text-xs font-medium text-gray-600">Network path</span>
        <input required className={`${input} font-mono`} value={draft.path} placeholder="\\fileserver\Finance"
          onChange={(e) => setDraft({ ...draft, path: e.target.value })} />
      </label>
      <label className="flex items-center gap-2 text-sm text-gray-700 pb-2">
        <input type="checkbox" checked={draft.enabled}
          onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />
        Enabled
      </label>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving}><Check className="w-4 h-4" /> Save</Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}><X className="w-4 h-4" /></Button>
      </div>
    </form>
  )
}

export default function SharesTab() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const shares = useQuery<Share[]>({ queryKey: ['shares'], queryFn: () => api.get('/admin/shares').then((r) => r.data) })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['shares'] })
    qc.invalidateQueries({ queryKey: ['reports'] })
  }
  const save = useMutation({
    mutationFn: ({ id, draft }: { id?: number; draft: Draft }) =>
      id ? api.put(`/admin/shares/${id}`, draft) : api.post('/admin/shares', draft),
    onSuccess: () => { setEditing(null); refresh() },
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/shares/${id}`),
    onSuccess: refresh,
  })
  const scan = useMutation({
    mutationFn: (shareId?: number) => api.post('/admin/scans', { share_id: shareId ?? null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })

  if (shares.isLoading) return <Loading />
  if (shares.error) return <ErrorNote error={shares.error} />

  return (
    <Card
      title="Shares"
      actions={<>
        <Button variant="secondary" size="sm" onClick={() => scan.mutate(undefined)} disabled={scan.isPending}>
          <Play className="w-4 h-4" /> Scan all
        </Button>
        <Button size="sm" onClick={() => setEditing('new')}><Plus className="w-4 h-4" /> Add share</Button>
      </>}
    >
      <div className="space-y-4">
        <p className="text-sm text-gray-500">
          Each share is read with the read-only service account. Scans run every night; use the play
          button to scan now and follow progress in Scan activity.
        </p>
        {save.error && <ErrorNote error={save.error} />}
        {scan.isSuccess && <p className="text-sm text-green-700">Scan queued. See Scan activity for progress.</p>}
        {editing === 'new' && (
          <ShareForm onCancel={() => setEditing(null)} saving={save.isPending}
            onSave={(draft) => save.mutate({ draft })} />
        )}
        <Table
          rows={shares.data ?? []}
          rowKey={(s) => s.id}
          empty="No shares configured yet."
          columns={[
            ['Name', (s) => editing === s.id
              ? <ShareForm initial={s} onCancel={() => setEditing(null)} saving={save.isPending}
                  onSave={(draft) => save.mutate({ id: s.id, draft })} />
              : <span className="font-medium">{s.name}</span>],
            ['Path', (s) => editing === s.id ? null : <span className="font-mono text-xs">{s.path}</span>],
            ['Status', (s) => editing === s.id ? null : (s.enabled ? <Badge variant="green">Enabled</Badge> : <Badge variant="gray">Disabled</Badge>)],
            ['', (s) => editing === s.id ? null : (
              <div className="flex justify-end gap-1">
                <Button variant="ghost" size="sm" title="Scan now" disabled={!s.enabled || scan.isPending}
                  onClick={() => scan.mutate(s.id)}><Play className="w-4 h-4" /></Button>
                <Button variant="ghost" size="sm" title="Edit" onClick={() => setEditing(s.id)}><Edit2 className="w-4 h-4" /></Button>
                <Button variant="ghost" size="sm" title="Remove from the index"
                  onClick={() => {
                    if (window.confirm(`Remove "${s.name}" and everything indexed from it? Files on the server are not touched.`)) {
                      remove.mutate(s.id)
                    }
                  }}><Trash2 className="w-4 h-4 text-red-600" /></Button>
              </div>
            ), 'text-right'],
          ]}
        />
      </div>
    </Card>
  )
}
