import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, Download, FolderPlus, Plus, Trash2 } from 'lucide-react'
import api from '../../lib/api'
import type { PlanEntryAdmin, Share } from '../../types'
import { cn } from '../../lib/utils'
import { Badge, Button } from '../../components/ui'
import { NAMING_HELP } from '../../components/plan'
import { Card, ErrorNote, ExportButton, Loading } from './common'
import { formatDateTime } from './ActivityTab'

const input = 'w-full px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'

type Draft = {
  name: string
  purpose: string
  belongs: string
  not_belongs: string
  owner: string
  naming: string
  naming_pattern: string
  examples: string
  extensions: string
  keywords: string
  allow_files: boolean
  allow_subfolders: boolean
  max_files: string
}

function toDraft(e: PlanEntryAdmin): Draft {
  return {
    name: e.path.split('/').pop() ?? '',
    purpose: e.purpose, belongs: e.belongs, not_belongs: e.not_belongs, owner: e.owner, naming: e.naming,
    naming_pattern: e.naming_pattern ?? '', examples: e.examples.join('\n'),
    extensions: e.extensions.join(', '), keywords: e.keywords.join(', '),
    allow_files: e.allow_files, allow_subfolders: e.allow_subfolders, max_files: e.max_files?.toString() ?? '',
  }
}

const split = (s: string, sep: RegExp) => s.split(sep).map((x) => x.trim()).filter(Boolean)

function toBody(entry: PlanEntryAdmin, d: Draft) {
  const parent = entry.path.includes('/') ? entry.path.slice(0, entry.path.lastIndexOf('/')) : ''
  return {
    ...(entry.path !== '' && { path: parent ? `${parent}/${d.name.trim()}` : d.name.trim() }),
    purpose: d.purpose, belongs: d.belongs, not_belongs: d.not_belongs, owner: d.owner, naming: d.naming,
    naming_pattern: d.naming_pattern.trim() || null,
    examples: split(d.examples, /\n/), extensions: split(d.extensions, /[,\s]+/), keywords: split(d.keywords, /,/),
    allow_files: d.allow_files, allow_subfolders: d.allow_subfolders,
    max_files: d.max_files.trim() ? Number(d.max_files) : null,
  }
}

export default function PlanTab() {
  const qc = useQueryClient()
  const shares = useQuery<Share[]>({ queryKey: ['shares'], queryFn: () => api.get('/admin/shares').then((r) => r.data) })
  const [shareId, setShareId] = useState<number | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const current = shareId ?? shares.data?.[0]?.id ?? null

  const plan = useQuery<PlanEntryAdmin[]>({
    queryKey: ['plan', current],
    queryFn: () => api.get('/admin/plan', { params: { share_id: current } }).then((r) => r.data),
    enabled: current !== null,
  })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['plan'] })
    qc.invalidateQueries({ queryKey: ['plan-guide'] })
    qc.invalidateQueries({ queryKey: ['reports', 'compliance'] })
  }
  const start = useMutation({
    mutationFn: async (depth: number | null) => {
      await (depth
        ? api.post('/admin/plan/import', { share_id: current, depth })
        : api.post('/admin/plan', { share_id: current, path: '' }))
    },
    onSuccess: refresh,
  })

  if (shares.isLoading || plan.isLoading) return <Loading />
  if (shares.error) return <ErrorNote error={shares.error} />
  if (!shares.data?.length) return <p className="text-sm text-gray-500">Add a share first (Shares tab).</p>
  if (plan.error) return <ErrorNote error={plan.error} />

  const entries = plan.data ?? []
  const entry = entries.find((e) => e.id === selected) ?? entries[0]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-gray-700">
          Share
          <select className={cn(input, 'w-auto')} value={current ?? ''}
            onChange={(e) => { setShareId(Number(e.target.value)); setSelected(null) }}>
            {shares.data.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <p className="text-sm text-gray-500 flex-1 min-w-[16rem]">
          The agreed folder structure. Everyone sees it in the Folder guide (only the folders they can open);
          the Compliance tab compares it with the share.
        </p>
        {entries.length > 0 && <ExportButton path="/admin/reports/plan" params={{ share_id: current }} />}
      </div>

      {start.error && <ErrorNote error={start.error} />}
      {entries.length === 0 ? (
        <StartPlan busy={start.isPending} onStart={(depth) => start.mutate(depth)} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(16rem,1fr)_2fr] items-start">
          <Card title="Folders">
            <ul className="-mx-5 -my-5 py-2">
              {entries.map((e) => (
                <li key={e.id}>
                  <button onClick={() => setSelected(e.id)}
                    className={cn('w-full flex items-center gap-2 py-1.5 pr-3 text-left text-sm hover:bg-gray-50',
                      e.id === entry?.id && 'bg-blue-50 text-blue-800')}
                    style={{ paddingLeft: `${1 + Math.min(e.depth, 8) * 1}rem` }}>
                    <span className="flex-1 truncate">{e.name}</span>
                    {!e.exists && <Badge variant="gray">not created</Badge>}
                    {e.example_problems.length > 0 && <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />}
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          {entry && <EntryEditor key={entry.id} entry={entry} onChanged={refresh}
            onSelect={setSelected} />}
        </div>
      )}
    </div>
  )
}

function StartPlan({ busy, onStart }: { busy: boolean; onStart: (depth: number | null) => void }) {
  const [depth, setDepth] = useState(2)
  return (
    <Card title="Start the folder plan for this share">
      <div className="space-y-4 text-sm text-gray-600">
        <p>
          Start from the folders already on the share (recommended: then describe them, remove the ones that won't
          stay, and add the new ones), or from an empty plan with only the share's root.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={busy} onClick={() => onStart(depth)}><Download className="w-4 h-4" /> Import existing folders</Button>
          <label className="flex items-center gap-2">
            down to
            <select className={cn(input, 'w-auto')} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
              {[1, 2, 3, 4].map((d) => <option key={d} value={d}>{d} level{d > 1 ? 's' : ''}</option>)}
            </select>
          </label>
          <span className="text-gray-400">or</span>
          <Button variant="secondary" disabled={busy} onClick={() => onStart(null)}><Plus className="w-4 h-4" /> Empty plan</Button>
        </div>
        <p className="text-xs text-gray-500">
          Folders at the deepest imported level allow subfolders of their own, so what is below them isn't
          reported as outside the plan.
        </p>
      </div>
    </Card>
  )
}

function Labeled({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn('block', className)}>
      <span className="text-xs font-medium text-gray-600">{label}</span>
      {children}
      {hint && <span className="block mt-0.5 text-xs text-gray-500">{hint}</span>}
    </label>
  )
}

function EntryEditor({ entry, onChanged, onSelect }: {
  entry: PlanEntryAdmin; onChanged: () => void; onSelect: (id: number | null) => void
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(entry))
  const [child, setChild] = useState('')
  // Saved changes (and changes by another admin) replace the draft; a background refetch alone does not.
  useEffect(() => setDraft(toDraft(entry)), [entry.updated_at])  // eslint-disable-line react-hooks/exhaustive-deps
  const set = <K extends keyof Draft>(k: K) => (v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }))
  const text = (k: keyof Draft) => ({
    value: draft[k] as string,
    onChange: (e: { target: { value: string } }) => set(k)(e.target.value as never),
  })

  const save = useMutation({
    mutationFn: () => api.put(`/admin/plan/${entry.id}`, toBody(entry, draft)),
    onSuccess: onChanged,
  })
  const addChild = useMutation({
    mutationFn: () => api.post('/admin/plan', { share_id: entry.share_id, path: entry.path ? `${entry.path}/${child}` : child }),
    onSuccess: (r) => { setChild(''); onChanged(); onSelect(r.data.id) },
  })
  const remove = useMutation({
    mutationFn: () => api.delete(`/admin/plan/${entry.id}`),
    onSuccess: () => { onSelect(null); onChanged() },
  })
  const isRoot = entry.path === ''

  return (
    <Card
      title={<span className="break-all">{entry.name}</span>}
      actions={<>
        {entry.exists ? <Badge variant="green">On the share</Badge> : <Badge variant="gray">Not created yet</Badge>}
        <Button variant="ghost" size="sm" title={isRoot ? 'Delete the whole plan' : 'Delete this folder and its subfolders from the plan'}
          onClick={() => {
            const what = isRoot ? 'the whole plan of this share' : `"${entry.path}" and everything planned below it`
            if (window.confirm(`Remove ${what} from the plan? Folders on the share are not touched.`)) remove.mutate()
          }}>
          <Trash2 className="w-4 h-4 text-red-600" />
        </Button>
      </>}
    >
      <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate() }}>
        <p className="font-mono text-xs text-gray-500 break-all">{entry.network_path}</p>
        {save.error && <ErrorNote error={save.error} />}
        {remove.error && <ErrorNote error={remove.error} />}
        {entry.example_problems.length > 0 && (
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-900">
            {entry.example_problems.map((p) => <p key={p}>{p}</p>)}
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {!isRoot && (
            <Labeled label="Folder name" hint="Renaming moves its planned subfolders with it.">
              <input required className={input} {...text('name')} />
            </Labeled>
          )}
          <Labeled label="Owner" hint="Who decides what goes here.">
            <input className={input} {...text('owner')} maxLength={200} />
          </Labeled>
        </div>
        <Labeled label="Purpose">
          <textarea rows={2} className={input} {...text('purpose')} />
        </Labeled>
        <div className="grid gap-3 sm:grid-cols-2">
          <Labeled label="What goes here"><textarea rows={3} className={input} {...text('belongs')} /></Labeled>
          <Labeled label="What doesn't (and where it goes instead)"><textarea rows={3} className={input} {...text('not_belongs')} /></Labeled>
        </div>
        <Labeled label="Naming convention" hint="As people should read it.">
          <textarea rows={2} className={input} {...text('naming')} />
        </Labeled>
        <div className="grid gap-3 sm:grid-cols-2">
          <Labeled label="Naming pattern (checked)" hint={NAMING_HELP}>
            <input className={cn(input, 'font-mono')} placeholder="{YYYY}-{MM}-{DD} *" {...text('naming_pattern')} />
          </Labeled>
          <Labeled label="Example file names" hint="One per line. Checked against the pattern and file types.">
            <textarea rows={3} className={cn(input, 'font-mono')} {...text('examples')} />
          </Labeled>
          <Labeled label="File types" hint="e.g. pdf, docx. Empty: any type.">
            <input className={input} {...text('extensions')} />
          </Labeled>
          <Labeled label="Keywords" hint="Comma-separated, in English and Spanish: they help people (and later the assistant) find this folder.">
            <input className={input} {...text('keywords')} />
          </Labeled>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-700">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={draft.allow_files} onChange={(e) => set('allow_files')(e.target.checked)} />
            Files can be saved directly here
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={draft.allow_subfolders} onChange={(e) => set('allow_subfolders')(e.target.checked)} />
            Other subfolders allowed (by project, year…)
          </label>
          <label className="flex items-center gap-2">
            Overgrown above
            <input type="number" min={1} className={cn(input, 'w-24')} placeholder="500" {...text('max_files')} />
            files
          </label>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-gray-100">
          <p className="text-xs text-gray-500">
            Last changed {formatDateTime(entry.updated_at)}{entry.updated_by ? ` by ${entry.updated_by}` : ''}
          </p>
          <Button type="submit" disabled={save.isPending}><Check className="w-4 h-4" /> {save.isPending ? 'Saving…' : 'Save'}</Button>
        </div>
      </form>

      <form className="mt-4 pt-4 border-t border-gray-100 flex flex-wrap items-end gap-2"
        onSubmit={(e: FormEvent) => { e.preventDefault(); if (child.trim()) addChild.mutate() }}>
        <Labeled label="Add a subfolder to the plan" className="flex-1 min-w-[12rem]">
          <input className={input} value={child} onChange={(e) => setChild(e.target.value)} placeholder="Folder name" />
        </Labeled>
        <Button type="submit" variant="secondary" disabled={addChild.isPending || !child.trim()}>
          <FolderPlus className="w-4 h-4" /> Add
        </Button>
        {addChild.error && <div className="w-full"><ErrorNote error={addChild.error} /></div>}
      </form>
    </Card>
  )
}
