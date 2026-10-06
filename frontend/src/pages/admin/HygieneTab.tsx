import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import type { HygieneReport } from '../../types'
import { Card, ErrorNote, ExportButton, Loading, PathText, Stat, Table } from './common'

export default function HygieneTab() {
  const { data, isLoading, error } = useQuery<HygieneReport>({
    queryKey: ['reports', 'hygiene'],
    queryFn: () => api.get('/admin/reports/hygiene').then((r) => r.data),
  })
  if (isLoading) return <Loading />
  if (error || !data) return <ErrorNote error={error} />

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <Stat label="Paths too long" value={data.long_paths.count.toLocaleString('en-GB')}
          hint={`Over ${data.long_paths.limit} characters`} />
        <Stat label="Deeply nested folders" value={data.deep_folders.count.toLocaleString('en-GB')}
          hint={`More than ${data.deep_folders.limit} levels`} />
        <Stat label="Empty folders" value={data.empty_folders.count.toLocaleString('en-GB')} />
      </div>
      <div className="flex justify-end"><ExportButton path="/admin/reports/hygiene" params={{ limit: 2000 }} /></div>

      <Card title="Paths too long">
        <p className="text-sm text-gray-500 mb-3">Windows and Office often fail to open or copy files with paths near 260 characters.</p>
        <Table rows={data.long_paths.items} rowKey={(r) => r.path} empty="None."
          columns={[['Path', (r) => <PathText path={r.path} />], ['Length', (r) => r.length, 'text-right tabular-nums']]} />
      </Card>
      <Card title="Deeply nested folders">
        <Table rows={data.deep_folders.items} rowKey={(r) => r.path} empty="None."
          columns={[['Folder', (r) => <PathText path={r.path} />], ['Depth', (r) => r.depth, 'text-right tabular-nums']]} />
      </Card>
      <Card title="Empty folders">
        <Table rows={data.empty_folders.items} rowKey={(r) => r.path} empty="None."
          columns={[['Folder', (r) => <PathText path={r.path} />]]} />
      </Card>
    </div>
  )
}
