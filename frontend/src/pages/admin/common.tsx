import { useState, type ReactNode } from 'react'
import { AlertCircle, Download } from 'lucide-react'
import { Button, Spinner } from '../../components/ui'
import { downloadCsv } from '../../lib/download'
import { cn } from '../../lib/utils'

export function Card({ title, actions, children, className }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={cn('bg-white rounded-xl border border-gray-200 shadow-sm', className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900 tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-gray-500">{hint}</p>}
    </div>
  )
}

export function Loading() {
  return <div className="flex justify-center py-12"><Spinner /></div>
}

export function ErrorNote({ error }: { error: unknown }) {
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return (
    <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
      <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
      <span>{detail ?? (error as Error)?.message ?? 'Something went wrong'}</span>
    </div>
  )
}

export function ExportButton({ path, params }: { path: string; params?: Record<string, unknown> }) {
  const [busy, setBusy] = useState(false)
  return (
    <Button
      variant="secondary" size="sm" disabled={busy}
      onClick={async () => {
        setBusy(true)
        try { await downloadCsv(path, params) } finally { setBusy(false) }
      }}
    >
      <Download className="w-4 h-4" /> {busy ? 'Exporting…' : 'Export CSV'}
    </Button>
  )
}

/** Simple table: columns are [header, cell renderer, optional class]. */
export function Table<T>({ rows, columns, empty = 'Nothing to show', rowKey }: {
  rows: T[]
  columns: [ReactNode, (row: T) => ReactNode, string?][]
  empty?: string
  rowKey: (row: T, i: number) => string | number
}) {
  if (rows.length === 0) return <p className="text-sm text-gray-500 py-4 text-center">{empty}</p>
  return (
    <div className="overflow-x-auto -mx-5">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-gray-500 border-b border-gray-100">
            {columns.map(([h, , cls], i) => <th key={i} className={cn('px-5 py-2 font-medium', cls)}>{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((r, i) => (
            <tr key={rowKey(r, i)} className="hover:bg-gray-50">
              {columns.map(([, cell, cls], j) => <td key={j} className={cn('px-5 py-2 align-top', cls)}>{cell(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function PathText({ path }: { path: string }) {
  return <span className="font-mono text-xs text-gray-700 break-all">{path}</span>
}
