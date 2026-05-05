import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileSearch, SlidersHorizontal, X } from 'lucide-react'
import api from '../lib/api'
import type { SearchResponse } from '../types'
import DocumentCard from '../components/catalog/DocumentCard'
import SearchBar from '../components/search/SearchBar'
import { Spinner, EmptyState, Button } from '../components/ui'

const FILE_TYPES = [
  { label: 'PDF', value: 'pdf' },
  { label: 'Word', value: 'docx' },
  { label: 'Excel', value: 'xlsx' },
  { label: 'PowerPoint', value: 'pptx' },
  { label: 'Text / CSV', value: 'txt' },
  { label: 'Image', value: 'jpg' },
  { label: 'ZIP / Archive', value: 'zip' },
]

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const q = searchParams.get('q') ?? ''
  const fileType = searchParams.get('type') ?? ''
  const page = parseInt(searchParams.get('page') ?? '1', 10)
  const [showFilters, setShowFilters] = useState(false)

  // Reset to page 1 when query changes
  useEffect(() => { setSearchParams((p) => { p.set('page', '1'); return p }) }, [q]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading, isError } = useQuery<SearchResponse>({
    queryKey: ['search', q, fileType, page],
    queryFn: () =>
      api
        .get('/search', { params: { q, file_type: fileType || undefined, page, page_size: 20 } })
        .then((r) => r.data),
    enabled: q.length > 0,
    staleTime: 30_000,
  })

  function setType(t: string) {
    setSearchParams((p) => {
      if (p.get('type') === t) p.delete('type')
      else p.set('type', t)
      p.set('page', '1')
      return p
    })
  }

  function setPage(n: number) {
    setSearchParams((p) => { p.set('page', String(n)); return p })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const totalPages = data ? Math.ceil(data.total / 20) : 0

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Search bar + filter toggle */}
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <SearchBar initialValue={q} />
        </div>
        <Button
          variant="secondary"
          onClick={() => setShowFilters((v) => !v)}
          className={showFilters ? 'border-blue-500 text-blue-600' : ''}
        >
          <SlidersHorizontal className="w-4 h-4" />
          Filters
          {fileType && (
            <span className="ml-1 bg-blue-600 text-white rounded-full w-4 h-4 text-xs flex items-center justify-center">
              1
            </span>
          )}
        </Button>
      </div>

      {/* Filter panel */}
      {showFilters && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-gray-700">Filter by file type</p>
            {fileType && (
              <button
                onClick={() => setType('')}
                className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700"
              >
                <X className="w-3 h-3" /> Clear
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {FILE_TYPES.map((ft) => (
              <button
                key={ft.value}
                onClick={() => setType(ft.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors
                  ${fileType === ft.value
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600'
                  }`}
              >
                {ft.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Results header */}
      {data && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-500">
            <span className="font-semibold text-gray-900">{data.total}</span> result
            {data.total !== 1 ? 's' : ''} for{' '}
            <span className="font-semibold text-gray-900">"{data.query}"</span>
          </p>
          {totalPages > 1 && (
            <p className="text-xs text-gray-400">
              Page {page} of {totalPages}
            </p>
          )}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex justify-center py-20">
          <Spinner className="w-8 h-8" />
        </div>
      )}

      {/* Error */}
      {isError && (
        <EmptyState
          icon={<FileSearch className="w-12 h-12" />}
          title="Search error"
          description="Something went wrong. Please try again."
        />
      )}

      {/* No results */}
      {data && data.results.length === 0 && (
        <EmptyState
          icon={<FileSearch className="w-16 h-16" />}
          title="No documents found"
          description={`We couldn't find anything matching "${q}". Try different keywords or browse the categories.`}
          action={
            <Button variant="secondary" onClick={() => window.history.back()}>
              ← Back
            </Button>
          }
        />
      )}

      {/* Results */}
      {data && data.results.length > 0 && (
        <div className="space-y-3">
          {data.results.map((doc) => (
            <DocumentCard key={doc.id} doc={doc} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 pt-4">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ← Previous
          </Button>
          <span className="flex items-center px-4 text-sm text-gray-500">
            {page} / {totalPages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Next →
          </Button>
        </div>
      )}
    </div>
  )
}
