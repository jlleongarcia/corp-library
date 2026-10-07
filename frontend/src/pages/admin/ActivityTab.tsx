import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Users, Copy } from 'lucide-react'
import api from '../../lib/api'
import type { Job, ScanRun, Share } from '../../types'
import { Badge, Button } from '../../components/ui'
import { Card, ErrorNote, Loading, Table } from './common'

const STATUS_VARIANT: Record<string, 'default' | 'green' | 'red' | 'gray'> = {
  queued: 'gray', running: 'default', done: 'green', success: 'green', partial: 'default', failed: 'red',
}

export function formatDateTime(s: string | null) {
  return s ? new Date(s).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' }) : '—'
}

export function ScanStatus({ status, at }: { status: string; at?: string | null }) {
  return (
    <span className="inline-flex items-center gap-2">
      <Badge variant={STATUS_VARIANT[status] ?? 'gray'}>{status}</Badge>
      {at && <span className="text-xs text-gray-500">{formatDateTime(at)}</span>}
    </span>
  )
}

function duration(a: string | null, b: string | null) {
  if (!a || !b) return '—'
  const s = Math.round((new Date(b).getTime() - new Date(a).getTime()) / 1000)
  return s < 120 ? `${s}s` : s < 7200 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`
}

const JOB_LABEL: Record<Job['kind'], string> = {
  scan: 'Scan', resolve_principals: 'Resolve users & groups', dedupe: 'Find duplicates',
}

export default function ActivityTab() {
  const qc = useQueryClient()
  const shares = useQuery<Share[]>({ queryKey: ['shares'], queryFn: () => api.get('/admin/shares').then((r) => r.data) })
  const jobs = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => api.get('/admin/jobs', { params: { limit: 30 } }).then((r) => r.data),
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === 'running' || j.status === 'queued') ? 3000 : 30000),
  })
  const runs = useQuery<ScanRun[]>({
    queryKey: ['scan-runs'],
    queryFn: () => api.get('/admin/scan-runs', { params: { limit: 30 } }).then((r) => r.data),
    refetchInterval: 10000,
  })
  const startJob = useMutation({
    mutationFn: (kind: string) => api.post(`/admin/jobs/${kind}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })

  const shareName = (payload: Record<string, unknown>) =>
    shares.data?.find((s) => s.id === payload.share_id)?.name ?? (payload.share_id ? `#${payload.share_id}` : '')

  return (
    <div className="space-y-6">
      <Card
        title="Jobs"
        actions={<>
          <Button variant="secondary" size="sm" onClick={() => startJob.mutate('resolve_principals')}>
            <Users className="w-4 h-4" /> Refresh users & groups
          </Button>
          <Button variant="secondary" size="sm" onClick={() => startJob.mutate('dedupe')}>
            <Copy className="w-4 h-4" /> Find duplicates
          </Button>
          <Button variant="ghost" size="sm" title="Reload" onClick={() => { jobs.refetch(); runs.refetch() }}>
            <RefreshCw className="w-4 h-4" />
          </Button>
        </>}
      >
        {jobs.isLoading ? <Loading /> : jobs.error ? <ErrorNote error={jobs.error} /> : (
          <Table
            rows={jobs.data ?? []}
            rowKey={(j) => j.id}
            empty="No jobs yet."
            columns={[
              ['Job', (j) => <><span className="font-medium">{JOB_LABEL[j.kind] ?? j.kind}</span> <span className="text-gray-500">{shareName(j.payload)}</span></>],
              ['Status', (j) => <ScanStatus status={j.status} />],
              ['Requested', (j) => <span className="text-xs text-gray-600">{formatDateTime(j.created_at)} · {j.requested_by ?? '—'}</span>],
              ['Duration', (j) => duration(j.started_at, j.finished_at), 'tabular-nums'],
              ['Error', (j) => j.error ? <details><summary className="text-red-700 cursor-pointer text-xs">{j.error.split('\n')[0]}</summary><pre className="text-xs whitespace-pre-wrap mt-1 text-gray-600">{j.error}</pre></details> : null],
            ]}
          />
        )}
      </Card>

      <Card title="Scan runs">
        {runs.isLoading ? <Loading /> : runs.error ? <ErrorNote error={runs.error} /> : (
          <Table
            rows={runs.data ?? []}
            rowKey={(r) => r.id}
            empty="No scans have run yet."
            columns={[
              ['Share', (r) => shareName({ share_id: r.share_id })],
              ['Status', (r) => <ScanStatus status={r.status} at={r.finished_at ?? r.started_at} />],
              ['Folders', (r) => (
                <span title={r.folders_skipped ? 'Junctions, symlinks or DFS links are listed but not followed' : undefined}>
                  {r.folders_seen.toLocaleString('en-GB')}
                  {r.folders_skipped > 0 && <span className="text-xs text-gray-500"> ({r.folders_skipped} links skipped)</span>}
                </span>
              ), 'text-right tabular-nums'],
              ['Files', (r) => r.files_seen.toLocaleString('en-GB'), 'text-right tabular-nums'],
              ['Changes', (r) => <span className="text-xs tabular-nums">+{r.files_added} ~{r.files_updated} −{r.files_removed}</span>],
              ['Duration', (r) => duration(r.started_at, r.finished_at), 'tabular-nums'],
              ['Errors', (r) => r.error_count ? <details><summary className="text-red-700 cursor-pointer text-xs">{r.error_count} error(s)</summary><pre className="text-xs whitespace-pre-wrap mt-1 text-gray-600">{r.error_sample}</pre></details> : <span className="text-gray-400">0</span>],
            ]}
          />
        )}
      </Card>
    </div>
  )
}
