import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera } from 'lucide-react'
import api from '../../lib/api'
import type { ComplianceProgress, ComplianceReport, ComplianceSnapshot, Share } from '../../types'
import { cn, formatDate } from '../../lib/utils'
import { Button } from '../../components/ui'
import { Card, ErrorNote, ExportButton, Loading, PathText, Stat, Table } from './common'

const number = (n: number) => n.toLocaleString('en-GB')
const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 1000) / 10 : null)
const showPct = (v: number | null) => (v === null ? '—' : `${v.toLocaleString('en-GB')}%`)

// Categorical slots 1 and 2 of the reference palette (validated as a pair).
const SERIES = [
  { key: 'in_plan', label: 'Files in the plan', color: '#2a78d6',
    value: (s: ComplianceSnapshot) => pct(s.files_in_plan, s.files_total) },
  { key: 'named', label: 'Correctly named', color: '#eb6834',
    value: (s: ComplianceSnapshot) => pct(s.files_checked - s.files_misnamed, s.files_checked) },
] as const

export default function ComplianceTab() {
  const shares = useQuery<Share[]>({ queryKey: ['shares'], queryFn: () => api.get('/admin/shares').then((r) => r.data) })
  const progress = useQuery<ComplianceProgress[]>({
    queryKey: ['reports', 'compliance', 'progress'],
    queryFn: () => api.get('/admin/reports/compliance/progress').then((r) => r.data),
  })
  const [shareId, setShareId] = useState<number | null>(null)
  const current = shareId ?? shares.data?.[0]?.id ?? null

  if (shares.isLoading) return <Loading />
  if (shares.error) return <ErrorNote error={shares.error} />
  if (!shares.data?.length) return <p className="text-sm text-gray-500">Add a share first (Shares tab).</p>

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-gray-700">
          Share
          <select className="px-3 py-2 rounded-lg border border-gray-300 text-sm" value={current ?? ''}
            onChange={(e) => setShareId(Number(e.target.value))}>
            {shares.data.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <p className="text-sm text-gray-500 flex-1 min-w-[16rem]">
          How the share follows its folder plan, as of the last scan.
        </p>
      </div>
      <ProgressCard progress={progress.data?.find((p) => p.share_id === current)} loading={progress.isLoading} />
      {current !== null && <Report shareId={current} />}
    </div>
  )
}

// ── Progress over time ────────────────────────────────────────────────────────

function ProgressCard({ progress, loading }: { progress?: ComplianceProgress; loading: boolean }) {
  const qc = useQueryClient()
  const snapshot = useMutation({
    mutationFn: () => api.post('/admin/jobs/compliance'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })
  const snaps = progress?.snapshots ?? []
  return (
    <Card
      title="Refactor progress"
      actions={<>
        <ExportButton path="/admin/reports/compliance/progress" />
        <Button variant="secondary" size="sm" disabled={snapshot.isPending} onClick={() => snapshot.mutate()}
          title="Record today's figures now instead of after tonight's scan">
          <Camera className="w-4 h-4" /> Record now
        </Button>
      </>}
    >
      {snapshot.isSuccess && <p className="mb-3 text-sm text-green-700">Queued. The chart updates when the worker has run it (Scan activity).</p>}
      {loading ? <Loading /> : snaps.length === 0 ? (
        <p className="text-sm text-gray-500">
          No figures yet. They are recorded once a day after the nightly scan, from the day the share has a plan.
        </p>
      ) : (
        <ProgressChart snapshots={snaps} />
      )}
    </Card>
  )
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(600)
  useEffect(() => {
    if (!ref.current) return
    const obs = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])
  return [ref, width] as const
}

function ProgressChart({ snapshots }: { snapshots: ComplianceSnapshot[] }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const height = 220
  const m = { top: 12, right: 56, bottom: 26, left: 40 }
  const w = Math.max(100, width - m.left - m.right)
  const h = height - m.top - m.bottom

  const times = snapshots.map((s) => new Date(`${s.day}T00:00:00`).getTime())
  const t0 = times[0]
  const t1 = times[times.length - 1]
  const x = (t: number) => m.left + (t1 === t0 ? w / 2 : ((t - t0) / (t1 - t0)) * w)
  const y = (v: number) => m.top + h - (v / 100) * h
  const ticks = [0, 25, 50, 75, 100]
  const xTicks = snapshots.length <= 1 ? [0] : [0, Math.floor((snapshots.length - 1) / 2), snapshots.length - 1]

  const lines = SERIES.map((s) => {
    const pts = snapshots.map((snap, i) => ({ i, v: s.value(snap) }))
    // A gap where the value is unknown (no files checked yet), not a drop to zero.
    let d = ''
    let pen = false
    for (const p of pts) {
      if (p.v === null) { pen = false; continue }
      d += `${pen ? 'L' : 'M'}${x(times[p.i])},${y(p.v)}`
      pen = true
    }
    const last = [...pts].reverse().find((p) => p.v !== null)
    return { ...s, d, pts, last }
  })
  // End labels too close to read apart: keep the first; the legend, tooltip and table carry the other.
  const [a, b] = lines
  if (a.last && b.last && Math.abs(y(a.last.v!) - y(b.last.v!)) < 12) b.last = undefined

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - box.left + m.left
    let best = 0
    times.forEach((t, i) => { if (Math.abs(x(t) - px) < Math.abs(x(times[best]) - px)) best = i })
    setHover(best)
  }
  const hs = hover !== null ? snapshots[hover] : null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-4 text-sm text-gray-700" aria-hidden>
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="inline-block w-4 h-0.5 rounded" style={{ background: s.color }} />{s.label}
          </span>
        ))}
      </div>
      <div ref={ref} className="relative">
        <svg width={width} height={height} role="img"
          aria-label={`Share of files in the plan and correctly named, ${snapshots[0].day} to ${snapshots[snapshots.length - 1].day}`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={m.left} x2={m.left + w} y1={y(t)} y2={y(t)} stroke="#e5e7eb" strokeWidth={1} />
              <text x={m.left - 6} y={y(t)} dy="0.32em" textAnchor="end" className="fill-gray-500 text-[11px] tabular-nums">{t}%</text>
            </g>
          ))}
          {xTicks.map((i) => (
            <text key={i} x={x(times[i])} y={height - 6} textAnchor={i === 0 && xTicks.length > 1 ? 'start' : i === snapshots.length - 1 && xTicks.length > 1 ? 'end' : 'middle'}
              className="fill-gray-500 text-[11px]">{formatDate(snapshots[i].day)}</text>
          ))}
          {hover !== null && <line x1={x(times[hover])} x2={x(times[hover])} y1={m.top} y2={m.top + h} stroke="#9ca3af" strokeWidth={1} />}
          {lines.map((l) => (
            <g key={l.key}>
              <path d={l.d} fill="none" stroke={l.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {l.pts.filter((p) => p.v !== null && (snapshots.length === 1 || p.i === hover)).map((p) => (
                <circle key={p.i} cx={x(times[p.i])} cy={y(p.v!)} r={4} fill={l.color} stroke="#fff" strokeWidth={2} />
              ))}
              {l.last && (
                <text x={x(times[l.last.i]) + 8} y={y(l.last.v!)} dy="0.32em" className="fill-gray-700 text-[11px] font-medium tabular-nums">
                  {showPct(l.last.v)}
                </text>
              )}
            </g>
          ))}
          <rect x={m.left - 8} y={m.top} width={w + 16} height={h} fill="transparent"
            onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
        </svg>
        {hs && (
          <div className="pointer-events-none absolute z-10 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs shadow-md"
            style={{ left: Math.min(x(times[hover!]) + 10, width - 200), top: m.top }}>
            <p className="font-medium text-gray-900">{formatDate(hs.day)}</p>
            {SERIES.map((s) => (
              <p key={s.key} className="flex items-center gap-1.5 text-gray-700">
                <span className="inline-block w-2 h-2 rounded-full" style={{ background: s.color }} />
                {s.label}: <span className="font-medium tabular-nums">{showPct(s.value(hs))}</span>
              </p>
            ))}
            <p className="mt-1 text-gray-500 tabular-nums">
              {number(hs.files_in_plan)} of {number(hs.files_total)} files in the plan · {number(hs.folders_missing)} planned folders missing
            </p>
          </div>
        )}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-gray-600">Show as a table</summary>
        <Table rows={[...snapshots].reverse()} rowKey={(s) => s.day} columns={[
          ['Day', (s) => formatDate(s.day)],
          ['Files', (s) => number(s.files_total), 'text-right tabular-nums'],
          ['In the plan', (s) => showPct(SERIES[0].value(s)), 'text-right tabular-nums'],
          ['Correctly named', (s) => showPct(SERIES[1].value(s)), 'text-right tabular-nums'],
          ['Wrong type', (s) => number(s.files_wrong_type), 'text-right tabular-nums'],
          ['Folders missing', (s) => number(s.folders_missing), 'text-right tabular-nums'],
          ['Empty', (s) => number(s.folders_empty), 'text-right tabular-nums'],
          ['Overgrown', (s) => number(s.folders_overgrown), 'text-right tabular-nums'],
        ]} />
      </details>
    </div>
  )
}

// ── Today's report ────────────────────────────────────────────────────────────

function Report({ shareId }: { shareId: number }) {
  const report = useQuery<ComplianceReport>({
    queryKey: ['reports', 'compliance', shareId],
    queryFn: () => api.get('/admin/reports/compliance', { params: { share_id: shareId } }).then((r) => r.data),
    retry: false,
  })
  if (report.isLoading) return <Loading />
  if (report.error) {
    const status = (report.error as { response?: { status?: number } }).response?.status
    return status === 404
      ? <p className="text-sm text-gray-500">This share has no folder plan yet. Start one in the Folder plan tab.</p>
      : <ErrorNote error={report.error} />
  }
  const r = report.data!
  const t = r.totals
  const more = (c: { count: number; items: unknown[] }) =>
    c.count > c.items.length ? ` (first ${number(c.items.length)} of ${number(c.count)}; export for all)` : ''

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Files in the plan" value={showPct(pct(t.files_in_plan, t.files_total))}
          hint={`${number(t.files_in_plan)} of ${number(t.files_total)}`} />
        <Stat label="Correctly named" value={showPct(pct(t.files_checked - t.files_misnamed, t.files_checked))}
          hint={`${number(t.files_misnamed)} misnamed, ${number(t.files_wrong_type)} of the wrong type`} />
        <Stat label="Planned folders" value={number(t.folders_planned)}
          hint={`${number(t.folders_missing)} not created yet, ${number(t.folders_empty)} empty`} />
        <Stat label="Overgrown folders" value={number(t.folders_overgrown)} hint="Too many files directly in them" />
      </div>
      <div className="flex justify-end"><ExportButton path="/admin/reports/compliance" params={{ share_id: shareId }} /></div>

      <Card title={`Outside the plan${more(r.outside)}`}>
        <p className="text-sm text-gray-500 mb-3">
          Folders the plan doesn't include (with everything below them), and planned folders that shouldn't hold files directly.
        </p>
        <Table rows={r.outside.items} rowKey={(i) => `${i.reason}-${i.folder_id}`} empty="Every file is in a planned folder."
          columns={[
            ['Folder', (i) => <PathText path={i.path} />],
            ['Why', (i) => <span className="text-xs">{i.reason === 'not_in_plan' ? 'Not in the plan' : 'No files allowed directly here'}</span>],
            ['Files', (i) => number(i.files), 'text-right tabular-nums'],
          ]} />
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title={`Naming${more(r.misnamed)}`}>
          <Table rows={r.misnamed.items} rowKey={(i) => i.path} empty="No naming problems."
            columns={[
              ['File', (i) => <PathText path={i.path} />],
              ['Expected', (i) => <code className="font-mono text-xs">{i.pattern}</code>],
            ]} />
        </Card>
        <Card title={`File types${more(r.wrong_type)}`}>
          <Table rows={r.wrong_type.items} rowKey={(i) => i.path} empty="No unexpected file types."
            columns={[
              ['File', (i) => <PathText path={i.path} />],
              ['Expected', (i) => <span className="text-xs">{i.allowed.map((e) => `.${e}`).join(', ')}</span>],
            ]} />
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <FolderList title="Planned, not created yet" items={r.missing.items} extra={more(r.missing)} />
        <FolderList title="Planned and empty" items={r.empty.items} extra={more(r.empty)} />
        <Card title={`Overgrown${more(r.overgrown)}`}>
          <Table rows={r.overgrown.items} rowKey={(i) => i.folder_id} empty="None."
            columns={[
              ['Folder', (i) => <PathText path={i.path} />],
              ['Files', (i) => <span className={cn(i.files > i.limit * 2 && 'font-semibold')}>{number(i.files)}</span>, 'text-right tabular-nums'],
            ]} />
        </Card>
      </div>
    </div>
  )
}

function FolderList({ title, items, extra }: { title: string; items: { plan_id: number; path: string }[]; extra: string }) {
  return (
    <Card title={`${title}${extra}`}>
      <Table rows={items} rowKey={(i) => i.plan_id} empty="None." columns={[['Folder', (i) => <PathText path={i.path} />]]} />
    </Card>
  )
}
