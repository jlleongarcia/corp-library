import api from './api'

/** Download a CSV export: fetched with axios so a failure can be shown instead of an error page. */
export async function downloadCsv(path: string, params: Record<string, unknown> = {}) {
  const res = await api.get(path, { params: { ...params, format: 'csv' }, responseType: 'blob', timeout: 300_000 })
  const disposition: string = res.headers['content-disposition'] ?? ''
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'export.csv'
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
