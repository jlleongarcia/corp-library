import { type FormEvent, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Download, Search, X } from 'lucide-react'
import api, { apiUrl } from '../lib/api'
import type { SearchFilters, SearchResponse, SearchResult } from '../types'
import { formatDate, formatFileSize } from '../lib/utils'
import { Button, EmptyState, Spinner } from '../components/ui'
import { CopyPathButton, FileTypeBadge, Snippet } from '../components/library'
import { ErrorNote } from './admin/common'

const PAGE_SIZE = 20
const FILTER_KEYS = ['share', 'type', 'from', 'to'] as const

const selectClass =
  'rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'

export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1)
  const sort = params.get('sort') ?? 'relevance'
  const hasFilters = FILTER_KEYS.some((k) => params.get(k))
  const [draft, setDraft] = useState(q)
  useEffect(() => setDraft(q), [q])

  const filters = useQuery<SearchFilters>({
    queryKey: ['search-filters'],
    queryFn: () => api.get('/search/filters').then((r) => r.data),
    staleTime: 5 * 60_000,
  })

  const searching = Boolean(q || hasFilters)
  const results = useQuery<SearchResponse>({
    queryKey: ['search', params.toString()],
    queryFn: () =>
      api.get('/search', {
        params: {
          q,
          share_id: params.get('share') || undefined,
          type: params.get('type') || undefined,
          modified_from: params.get('from') || undefined,
          modified_to: params.get('to') || undefined,
          sort: searching ? sort : 'newest',
          limit: searching ? PAGE_SIZE : 10,
          offset: (page - 1) * PAGE_SIZE,
        },
      }).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  /** Change some URL parameters; any change other than the page goes back to page 1. */
  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next)
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    update({ q: draft.trim() || null })
  }

  const total = results.data?.total ?? 0
  const pages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="space-y-5">
      <form onSubmit={submit} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="search"
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Search documents by name, folder or content…"
            aria-label="Search documents"
            className="w-full pl-10 pr-4 py-3 rounded-xl border border-gray-300 text-base shadow-sm
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <Button type="submit" className="px-5">Search</Button>
      </form>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <select
          className={selectClass}
          value={params.get('share') ?? ''}
          onChange={(e) => update({ share: e.target.value || null })}
          aria-label="Share"
        >
          <option value="">All shares</option>
          {filters.data?.shares.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <select
          className={selectClass}
          value={params.get('type') ?? ''}
          onChange={(e) => update({ type: e.target.value || null })}
          aria-label="File type"
        >
          <option value="">All types</option>
          {filters.data?.types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-gray-600">
          Modified from
          <input type="date" className={selectClass} value={params.get('from') ?? ''}
                 onChange={(e) => update({ from: e.target.value || null })} />
        </label>
        <label className="flex items-center gap-1.5 text-gray-600">
          to
          <input type="date" className={selectClass} value={params.get('to') ?? ''}
                 onChange={(e) => update({ to: e.target.value || null })} />
        </label>
        {searching && (
          <select className={selectClass} value={sort} onChange={(e) => update({ sort: e.target.value })}
                  aria-label="Sort by">
            <option value="relevance">Best match</option>
            <option value="newest">Newest first</option>
            <option value="name">Name</option>
          </select>
        )}
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={() => update({ share: null, type: null, from: null, to: null })}>
            <X className="w-4 h-4" /> Clear filters
          </Button>
        )}
      </div>

      {results.error ? <ErrorNote error={results.error} /> : results.isLoading ? (
        <div className="flex justify-center py-16"><Spinner /></div>
      ) : !searching ? (
        <RecentDocuments results={results.data?.results ?? []} />
      ) : total === 0 ? (
        <EmptyState
          icon={<Search className="w-12 h-12" />}
          title="No documents found"
          description="Try other words, fewer words, or remove filters. You only see documents you can open on the file server."
        />
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-gray-500">
            {total.toLocaleString('en-GB')} document{total === 1 ? '' : 's'}
            {results.isFetching && <Spinner className="w-3.5 h-3.5 ml-2 align-middle" />}
          </p>
          <ul className="space-y-3">
            {results.data!.results.map((r) => <ResultCard key={r.file_id} result={r} />)}
          </ul>
          {pages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-2">
              <Button variant="secondary" size="sm" disabled={page <= 1}
                      onClick={() => update({ page: String(page - 1) })}>
                <ChevronLeft className="w-4 h-4" /> Previous
              </Button>
              <span className="text-sm text-gray-600 tabular-nums">Page {page} of {pages}</span>
              <Button variant="secondary" size="sm" disabled={page >= pages}
                      onClick={() => update({ page: String(page + 1) })}>
                Next <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ResultCard({ result: r }: { result: SearchResult }) {
  return (
    <li className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 hover:border-blue-300 transition-colors">
      <div className="flex items-start gap-3">
        <FileTypeBadge ext={r.extension} className="mt-0.5" />
        <div className="min-w-0 flex-1 space-y-1">
          <Link to={`/documents/${r.file_id}`} className="font-semibold text-blue-700 hover:underline break-words">
            {r.name}
          </Link>
          <p className="text-xs text-gray-500 break-all">
            <Link to={`/browse/${r.folder_id}`} className="hover:underline">
              {r.share}{r.folder_path ? ` › ${r.folder_path.split('/').join(' › ')}` : ''}
            </Link>
            <span className="mx-1.5">·</span>{formatFileSize(r.size)}
            <span className="mx-1.5">·</span>Modified {formatDate(r.mtime)}
          </p>
          <Snippet segments={r.snippet} />
        </div>
        <div className="hidden sm:flex flex-col gap-2 flex-shrink-0">
          <a href={apiUrl(`/documents/${r.file_id}/download`)}
             className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium bg-blue-600 text-white hover:bg-blue-700">
            <Download className="w-4 h-4" /> Download
          </a>
          <CopyPathButton path={r.path} label="Copy path" />
        </div>
      </div>
    </li>
  )
}

function RecentDocuments({ results }: { results: SearchResult[] }) {
  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-blue-50 border border-blue-100 px-5 py-4 text-sm text-blue-900">
        <p className="font-medium">Search everything you can open on the department shares.</p>
        <p className="mt-1 text-blue-800">
          Words match names, folders and the text inside documents, in English or Spanish, with or without
          accents. Use <code className="bg-white/70 px-1 rounded">"quotes"</code> for an exact phrase and{' '}
          <code className="bg-white/70 px-1 rounded">-word</code> to exclude a word.
        </p>
      </div>
      {results.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">Recently modified</h2>
          <ul className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
            {results.map((r) => (
              <li key={r.file_id}>
                <Link to={`/documents/${r.file_id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50">
                  <FileTypeBadge ext={r.extension} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-gray-900 truncate">{r.name}</span>
                    <span className="block text-xs text-gray-500 truncate">
                      {r.share}{r.folder_path ? ` › ${r.folder_path.split('/').join(' › ')}` : ''}
                    </span>
                  </span>
                  <span className="text-xs text-gray-500 whitespace-nowrap">{formatDate(r.mtime)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
