import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { formatFileSize } from '../../lib/utils'
import type { DuplicatesReport } from '../../types'
import { Badge, Button } from '../../components/ui'
import { Card, ErrorNote, ExportButton, Loading, PathText, Stat } from './common'
import { formatDateTime } from './ActivityTab'

const PAGE = 25

export default function DuplicatesTab() {
  const [page, setPage] = useState(0)
  const { data, isLoading, error } = useQuery<DuplicatesReport>({
    queryKey: ['reports', 'duplicates', page],
    queryFn: () => api.get('/admin/reports/duplicates', { params: { limit: PAGE, offset: page * PAGE } }).then((r) => r.data),
    placeholderData: keepPreviousData,
  })
  if (isLoading) return <Loading />
  if (error || !data) return <ErrorNote error={error} />
  const pages = Math.ceil(data.total_groups / PAGE)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <Stat label="Duplicate sets" value={data.total_groups.toLocaleString('en-GB')} />
        <Stat label="Space taken by extra copies" value={formatFileSize(data.total_wasted_bytes)} />
      </div>
      <Card
        title="Largest duplicate sets"
        actions={<ExportButton path="/admin/reports/duplicates" params={{ limit: 500 }} />}
      >
        <p className="text-sm text-gray-500 mb-4">
          Files with identical content. <b>Exact</b> means a full content hash matched; <b>probable</b> means
          very large files whose size and start/end match. Duplicates are refreshed after each nightly scan.
        </p>
        {data.groups.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-4">No duplicates found (yet).</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {data.groups.map((g, i) => (
              <li key={i} className="py-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">{g.copies} copies × {formatFileSize(g.size)}</span>
                  <Badge variant={g.confidence === 'exact' ? 'green' : 'gray'}>{g.confidence}</Badge>
                  <span className="text-gray-500">{formatFileSize(g.wasted_bytes)} recoverable</span>
                </div>
                <ul className="mt-2 space-y-1">
                  {g.files.map((f) => (
                    <li key={f.path} className="flex justify-between gap-4">
                      <PathText path={f.path} />
                      <span className="text-xs text-gray-500 whitespace-nowrap">{formatDateTime(f.mtime)}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
        {pages > 1 && (
          <div className="flex items-center justify-end gap-2 pt-4">
            <Button variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
            <span className="text-sm text-gray-500">{page + 1} / {pages}</span>
            <Button variant="secondary" size="sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        )}
      </Card>
    </div>
  )
}
