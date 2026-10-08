import { useState } from 'react'
import { Link } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import type { AuditEvent, AuditLog } from '../../types'
import { Badge, Button } from '../../components/ui'
import { Card, ErrorNote, ExportButton, Loading, PathText, Table } from './common'
import { formatDateTime } from './ActivityTab'

const PAGE = 100

const ACTIONS: { key: AuditEvent['action']; label: string }[] = [
  { key: 'search', label: 'Searches' },
  { key: 'view', label: 'Document views' },
  { key: 'preview', label: 'Previews' },
  { key: 'download', label: 'Downloads' },
  { key: 'denied', label: 'Denied by the file server' },
  { key: 'sign_in', label: 'Sign-ins' },
  { key: 'sign_in_failed', label: 'Failed sign-ins' },
  { key: 'sign_out', label: 'Sign-outs' },
  { key: 'audit_read', label: 'Audit log queries' },
]

const VARIANT: Partial<Record<AuditEvent['action'], 'default' | 'green' | 'red' | 'gray'>> = {
  download: 'green', denied: 'red', sign_in_failed: 'red', search: 'default',
}

function what(e: AuditEvent) {
  if (e.action === 'search') {
    const { q, results, ...filters } = e.detail as { q?: string; results?: number } & Record<string, unknown>
    const extra = Object.entries(filters).map(([k, v]) => `${k}=${v}`).join(', ')
    return (
      <span>
        <span className="font-medium">“{q || '—'}”</span>
        <span className="text-gray-500"> · {results ?? 0} results{extra && ` · ${extra}`}</span>
      </span>
    )
  }
  if (e.path) return <PathText path={e.path} />
  const detail = Object.entries(e.detail).map(([k, v]) => `${k}: ${v}`).join(', ')
  return <span className="text-gray-500 text-xs">{detail}</span>
}

export default function AuditTab() {
  const [username, setUsername] = useState('')
  const [action, setAction] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [page, setPage] = useState(0)
  const filters = {
    username: username.trim() || undefined, action: action || undefined,
    since: since || undefined, until: until || undefined,
  }

  const log = useQuery<AuditLog>({
    queryKey: ['audit', filters, page],
    queryFn: () => api.get('/admin/reports/audit', { params: { ...filters, limit: PAGE, offset: page * PAGE } })
      .then((r) => r.data),
    placeholderData: keepPreviousData,
  })
  const pages = Math.ceil((log.data?.total ?? 0) / PAGE)
  const input = 'rounded-lg border border-gray-300 px-2.5 py-1.5 text-sm'

  return (
    <Card
      title="Audit log"
      actions={<ExportButton path="/admin/reports/audit" params={{ ...filters, limit: 10_000 }} />}
    >
      <div className="flex flex-wrap items-end gap-2 mb-4 text-sm">
        <input className={input} placeholder="Username" value={username}
               onChange={(e) => { setUsername(e.target.value); setPage(0) }} />
        <select className={input} value={action} onChange={(e) => { setAction(e.target.value); setPage(0) }}>
          <option value="">All events</option>
          {ACTIONS.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-gray-600">From
          <input type="date" className={input} value={since} onChange={(e) => { setSince(e.target.value); setPage(0) }} />
        </label>
        <label className="flex items-center gap-1.5 text-gray-600">to
          <input type="date" className={input} value={until} onChange={(e) => { setUntil(e.target.value); setPage(0) }} />
        </label>
      </div>
      {log.isLoading ? <Loading /> : log.error ? <ErrorNote error={log.error} /> : (
        <>
          <Table
            rows={log.data?.events ?? []}
            rowKey={(e) => e.id}
            empty="No events match."
            columns={[
              ['When', (e) => <span className="text-xs whitespace-nowrap">{formatDateTime(e.at)}</span>],
              ['User', (e) => e.username ?? '—'],
              ['Event', (e) => <Badge variant={VARIANT[e.action] ?? 'gray'}>{e.action.replace(/_/g, ' ')}</Badge>],
              ['What', (e) => e.file_id && e.action !== 'denied'
                ? <Link to={`/documents/${e.file_id}`} className="hover:underline">{what(e)}</Link>
                : what(e)],
              ['IP', (e) => <span className="text-xs text-gray-500">{e.client_ip ?? ''}</span>],
            ]}
          />
          {pages > 1 && (
            <div className="flex items-center justify-end gap-2 pt-3 text-sm">
              <span className="text-gray-500">{log.data!.total.toLocaleString('en-GB')} events · page {page + 1} of {pages}</span>
              <Button variant="secondary" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button variant="secondary" size="sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          )}
        </>
      )}
    </Card>
  )
}
