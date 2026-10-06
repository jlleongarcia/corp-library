import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { formatFileSize } from '../../lib/utils'
import type { StaleFolder } from '../../types'
import { Card, ErrorNote, ExportButton, Loading, PathText, Table } from './common'
import { formatDateTime } from './ActivityTab'

export default function StaleTab() {
  const [years, setYears] = useState(5)
  const { data, isLoading, error } = useQuery<StaleFolder[]>({
    queryKey: ['reports', 'stale', years],
    queryFn: () => api.get('/admin/reports/stale', { params: { years } }).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  return (
    <Card
      title="Folders with stale files"
      actions={<>
        <label className="text-sm text-gray-600 flex items-center gap-2">
          Not modified in
          <select value={years} onChange={(e) => setYears(Number(e.target.value))}
            className="border border-gray-300 rounded-lg px-2 py-1 text-sm">
            {[2, 3, 5, 7, 10].map((y) => <option key={y} value={y}>{y} years</option>)}
          </select>
        </label>
        <ExportButton path="/admin/reports/stale" params={{ years, limit: 1000 }} />
      </>}
    >
      <p className="text-sm text-gray-500 mb-4">
        Candidates for archiving during the reorganization, largest first.
      </p>
      {isLoading ? <Loading /> : error || !data ? <ErrorNote error={error} /> : (
        <Table
          rows={data}
          rowKey={(r) => r.folder}
          empty="No stale files for this period."
          columns={[
            ['Folder', (r) => <PathText path={r.folder} />],
            ['Files', (r) => r.stale_files.toLocaleString('en-GB'), 'text-right tabular-nums'],
            ['Size', (r) => formatFileSize(r.stale_bytes), 'text-right tabular-nums whitespace-nowrap'],
            ['Most recent', (r) => formatDateTime(r.newest_stale), 'whitespace-nowrap text-xs text-gray-600'],
          ]}
        />
      )}
    </Card>
  )
}
