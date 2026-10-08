import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download, ExternalLink, FileQuestion, Info } from 'lucide-react'
import api, { apiUrl } from '../lib/api'
import type { DocumentDetail, IndexStatus } from '../types'
import { formatFileSize } from '../lib/utils'
import { EmptyState } from '../components/ui'
import { CopyPathButton, FileTypeBadge } from '../components/library'
import { ErrorNote, Loading } from './admin/common'
import { formatDateTime } from './admin/ActivityTab'

const INDEX_NOTE: Record<IndexStatus, string> = {
  pending: 'The text of this document is being indexed; for now it is found by name and folder only.',
  text: '',
  ocr: 'The text was read from a scan (OCR) and may contain recognition errors.',
  empty: 'This document contains no text to search.',
  metadata: 'Files of this type are found by name and folder only.',
  too_large: 'This file is too large to index its content; it is found by name and folder only.',
  ocr_unavailable: 'This is a scanned document; its text has not been read yet.',
  error: 'The text of this document could not be read (it may be password-protected or damaged).',
}

export default function DocumentPage() {
  const { fileId } = useParams()
  const doc = useQuery<DocumentDetail>({
    queryKey: ['document', fileId],
    queryFn: () => api.get(`/documents/${fileId}`).then((r) => r.data),
    retry: false,
  })

  if (doc.isLoading) return <Loading />
  if (doc.error) {
    const status = (doc.error as { response?: { status?: number } }).response?.status
    return status === 404 ? (
      <EmptyState
        icon={<FileQuestion className="w-12 h-12" />}
        title="Document not found"
        description="It may have been moved or deleted, or you don't have access to it on the file server."
        action={<Link to="/" className="text-blue-700 hover:underline">Back to search</Link>}
      />
    ) : <ErrorNote error={doc.error} />
  }
  const d = doc.data!
  const note = d.index_status ? INDEX_NOTE[d.index_status] : INDEX_NOTE.pending

  return (
    <div className="space-y-5">
      <button onClick={() => history.back()} className="inline-flex items-center gap-1 text-sm text-blue-700 hover:underline">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 space-y-4">
        <div className="flex items-start gap-3">
          <FileTypeBadge ext={d.extension} className="mt-1" />
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-gray-900 break-words">{d.name}</h1>
            <p className="mt-1 font-mono text-xs text-gray-500 break-all">{d.path}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <a href={apiUrl(`/documents/${d.file_id}/download`)}
             className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium bg-blue-600 text-white hover:bg-blue-700">
            <Download className="w-4 h-4" /> Download
          </a>
          <CopyPathButton path={d.path} size="md" />
          {d.preview && (
            <a href={apiUrl(`/documents/${d.file_id}/preview`)} target="_blank" rel="noopener"
               className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium bg-white text-gray-700 border border-gray-300 hover:bg-gray-50">
              <ExternalLink className="w-4 h-4" /> Open in new tab
            </a>
          )}
        </div>
        <p className="text-xs text-gray-500">
          To edit the document in place, copy its network path and paste it into File Explorer or Office's Open dialog.
        </p>

        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm border-t border-gray-100 pt-4">
          <div><dt className="text-xs text-gray-500">Share</dt><dd className="font-medium">{d.share}</dd></div>
          <div>
            <dt className="text-xs text-gray-500">Folder</dt>
            <dd><Link to={`/browse/${d.folder_id}`} className="text-blue-700 hover:underline break-all">
              {d.folder_path ? d.folder_path.split('/').pop() : d.share}
            </Link></dd>
          </div>
          <div><dt className="text-xs text-gray-500">Size</dt><dd className="font-medium">{formatFileSize(d.size)}</dd></div>
          <div><dt className="text-xs text-gray-500">Modified</dt><dd className="font-medium">{formatDateTime(d.mtime)}</dd></div>
        </dl>
      </div>

      {d.preview === 'pdf' && (
        <iframe title="Preview" src={apiUrl(`/documents/${d.file_id}/preview`)}
                className="w-full h-[75vh] rounded-xl border border-gray-200 bg-white" />
      )}
      {d.preview === 'image' && (
        <img src={apiUrl(`/documents/${d.file_id}/preview`)} alt={d.name}
             className="max-w-full max-h-[75vh] rounded-xl border border-gray-200 bg-white mx-auto" />
      )}

      {note && (
        <p className="flex items-start gap-2 text-sm text-gray-600 bg-gray-100 rounded-lg px-4 py-3">
          <Info className="w-4 h-4 mt-0.5 flex-shrink-0" /> {note}
        </p>
      )}
      {d.text_excerpt && !d.preview && (
        <section className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <h2 className="px-5 py-3 border-b border-gray-100 font-semibold text-gray-900">Text</h2>
          <pre className="px-5 py-4 text-sm text-gray-700 whitespace-pre-wrap break-words font-sans max-h-[60vh] overflow-y-auto">
            {d.text_excerpt}{d.text_truncated && '…'}
          </pre>
        </section>
      )}
    </div>
  )
}
