import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { formatFileSize } from '../../lib/utils'
import type { SummaryReport } from '../../types'
import { Card, ErrorNote, ExportButton, Loading, Stat, Table } from './common'
import { ScanStatus } from './ActivityTab'

const number = (n: number) => n.toLocaleString('en-GB')

export default function OverviewTab() {
  const { data, isLoading, error } = useQuery<SummaryReport>({
    queryKey: ['reports', 'summary'],
    queryFn: () => api.get('/admin/reports/summary').then((r) => r.data),
  })
  if (isLoading) return <Loading />
  if (error || !data) return <ErrorNote error={error} />

  const totals = data.shares.reduce(
    (t, s) => ({ files: t.files + s.files, bytes: t.bytes + s.bytes, folders: t.folders + s.folders }),
    { files: 0, bytes: 0, folders: 0 },
  )
  const maxAge = Math.max(1, ...data.by_age.map((b) => b.bytes))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Shares" value={data.shares.length} />
        <Stat label="Folders" value={number(totals.folders)} />
        <Stat label="Files" value={number(totals.files)} />
        <Stat label="Total size" value={formatFileSize(totals.bytes)} />
      </div>

      <Card title="Shares">
        <Table
          rows={data.shares}
          rowKey={(s) => s.share_id}
          empty="No shares yet. Add one in the Shares tab."
          columns={[
            ['Share', (s) => <><p className="font-medium">{s.share}</p><p className="font-mono text-xs text-gray-500">{s.path}</p></>],
            ['Folders', (s) => number(s.folders), 'text-right tabular-nums'],
            ['Files', (s) => number(s.files), 'text-right tabular-nums'],
            ['Size', (s) => formatFileSize(s.bytes), 'text-right tabular-nums whitespace-nowrap'],
            ['Last scan', (s) => s.last_scan_status ? <ScanStatus status={s.last_scan_status} at={s.last_scan_finished} /> : <span className="text-gray-400">Never</span>],
          ]}
        />
      </Card>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card title="File types by size" actions={<ExportButton path="/admin/reports/extensions" />}>
          <Table
            rows={data.by_extension}
            rowKey={(e) => e.extension}
            columns={[
              ['Type', (e) => <span className="font-mono">{e.extension}</span>],
              ['Files', (e) => number(e.files), 'text-right tabular-nums'],
              ['Size', (e) => formatFileSize(e.bytes), 'text-right tabular-nums whitespace-nowrap'],
            ]}
          />
        </Card>

        <Card title="Age (last modified)">
          <ul className="space-y-3">
            {data.by_age.map((b) => (
              <li key={b.bucket}>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-700">{b.bucket}</span>
                  <span className="tabular-nums text-gray-500">{number(b.files)} files · {formatFileSize(b.bytes)}</span>
                </div>
                <div className="mt-1 h-2 rounded bg-gray-100">
                  <div className="h-2 rounded bg-blue-500" style={{ width: `${(b.bytes / maxAge) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
