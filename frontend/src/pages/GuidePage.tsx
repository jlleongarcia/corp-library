import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Folder, Map as MapIcon, Search, X } from 'lucide-react'
import api from '../lib/api'
import type { PlanGuideEntry, PlanGuideShare } from '../types'
import { cn } from '../lib/utils'
import { EmptyState } from '../components/ui'
import { entryMatches, PlanDetails, PlanEntryActions } from '../components/plan'
import { ErrorNote, Loading } from './admin/common'

/**
 * The folder guide: the department's agreed folder structure, what goes where and
 * how to name it. Read-only; it shows the folders the user can see in Explorer.
 */
export default function GuidePage() {
  const { hash } = useLocation()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<Set<number>>(new Set())
  const guide = useQuery<PlanGuideShare[]>({ queryKey: ['plan-guide'], queryFn: () => api.get('/plan').then((r) => r.data) })

  // /guide#plan-12 (from the browse page) opens and shows that entry.
  useEffect(() => {
    const id = Number(/^#plan-(\d+)$/.exec(hash)?.[1])
    if (!id || !guide.data) return
    setOpen((o) => new Set(o).add(id))
    requestAnimationFrame(() => document.getElementById(`plan-${id}`)?.scrollIntoView({ block: 'start' }))
  }, [hash, guide.data])

  const shares = useMemo(
    () => (guide.data ?? [])
      .map((s) => ({ ...s, entries: s.entries.filter((e) => entryMatches(e, query)) }))
      .filter((s) => s.entries.length > 0),
    [guide.data, query],
  )

  if (guide.isLoading) return <Loading />
  if (guide.error) return <ErrorNote error={guide.error} />
  if (!guide.data?.length) {
    return (
      <EmptyState
        icon={<MapIcon className="w-12 h-12" />}
        title="No folder guide yet"
        description="The department's folder plan hasn't been published here yet, or it only covers folders you can't open."
      />
    )
  }

  const toggle = (id: number) => setOpen((o) => {
    const next = new Set(o)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Folder guide</h1>
        <p className="text-sm text-gray-500">Where documents belong on the department shares, and how to name them.</p>
      </div>

      <div className="relative max-w-xl">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="What are you saving? e.g. invoice, contrato, acta"
          aria-label="Filter the folder guide"
          className="w-full pl-9 pr-9 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {query && (
          <button onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-700" title="Clear">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {shares.length === 0 && <p className="text-sm text-gray-500">No folder in the guide matches “{query}”.</p>}

      {shares.map((s) => (
        <section key={s.share_id} className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="px-5 py-3 border-b border-gray-100">
            <h2 className="font-semibold text-gray-900">{s.share}</h2>
            <p className="font-mono text-xs text-gray-500 break-all">{s.path}</p>
          </div>
          <ul className="divide-y divide-gray-100">
            {s.entries.map((e) => (
              <GuideRow key={e.id} entry={e} open={open.has(e.id) || (query !== '' && s.entries.length <= 3)}
                indent={query ? 0 : e.depth} onToggle={() => toggle(e.id)} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function GuideRow({ entry, open, indent, onToggle }: {
  entry: PlanGuideEntry; open: boolean; indent: number; onToggle: () => void
}) {
  return (
    <li id={`plan-${entry.id}`} className="scroll-mt-20">
      <button
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-start gap-2 px-5 py-2.5 text-left hover:bg-gray-50"
        style={{ paddingLeft: `${1.25 + Math.min(indent, 6) * 1.25}rem` }}
      >
        {open ? <ChevronDown className="w-4 h-4 mt-0.5 text-gray-400 flex-shrink-0" />
          : <ChevronRight className="w-4 h-4 mt-0.5 text-gray-400 flex-shrink-0" />}
        <Folder className="w-4 h-4 mt-0.5 text-amber-500 flex-shrink-0" />
        <span className="min-w-0">
          <span className="font-medium text-gray-900 break-all">{indent === 0 && entry.path ? entry.path : entry.name}</span>
          {entry.purpose && <span className={cn('block text-sm text-gray-500', !open && 'line-clamp-1')}>{entry.purpose}</span>}
        </span>
      </button>
      {open && (
        <div className="pb-4 pr-5 space-y-3" style={{ paddingLeft: `${3.25 + Math.min(indent, 6) * 1.25}rem` }}>
          <PlanDetails entry={{ ...entry, purpose: '' }} />
          <PlanEntryActions entry={entry} />
        </div>
      )}
    </li>
  )
}
