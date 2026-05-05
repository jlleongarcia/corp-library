import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft, Calendar, Copy, FileText, Folder, Lock, Tag,
} from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../lib/api'
import type { DocumentDetail } from '../types'
import { Button, Spinner } from '../components/ui'
import { fileTypeBadgeClass, formatDate, formatFileSize } from '../lib/utils'
import { cn } from '../lib/utils'
import { useState } from 'react'

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 py-3 border-b border-gray-100 last:border-0">
      <dt className="text-xs font-semibold text-gray-400 uppercase tracking-wide w-36 flex-shrink-0">
        {label}
      </dt>
      <dd className="text-sm text-gray-700">{children}</dd>
    </div>
  )
}

export default function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const [copied, setCopied] = useState(false)

  const { data: doc, isLoading, isError, error } = useQuery<DocumentDetail>({
    queryKey: ['documents', documentId],
    queryFn: () => api.get(`/documents/${documentId}`).then((r) => r.data),
  })

  function copyPath() {
    if (!doc) return
    navigator.clipboard.writeText(doc.file_path)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-32">
        <Spinner className="w-8 h-8" />
      </div>
    )
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const statusCode = (error as any)?.response?.status

  if (isError) {
    return (
      <div className="max-w-xl mx-auto py-16 text-center">
        <div className="text-6xl mb-4">{statusCode === 403 ? '🔒' : '😕'}</div>
        <h2 className="text-xl font-bold text-gray-800 mb-2">
          {statusCode === 403 ? 'Access Denied' : 'Document Not Found'}
        </h2>
        <p className="text-gray-500 text-sm mb-6">
          {statusCode === 403
            ? "You don't have permission to view this document. Contact your manager or IT to request access."
            : "This document doesn't exist or has been removed."}
        </p>
        <Button variant="secondary" onClick={() => navigate(-1)}>
          ← Go Back
        </Button>
      </div>
    )
  }

  if (!doc) return null

  const ext = doc.file_extension?.toUpperCase() ?? 'FILE'

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Back */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-blue-600 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      {/* Document card */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden shadow-sm">
        {/* Header */}
        <div className="bg-gray-50 border-b border-gray-200 px-6 py-5 flex items-start gap-4">
          <span
            className={cn(
              'flex-shrink-0 inline-flex items-center justify-center w-14 h-14 rounded-xl text-sm font-bold',
              fileTypeBadgeClass(doc.file_extension),
            )}
          >
            {ext}
          </span>
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-gray-900 leading-tight">{doc.title}</h1>
            {doc.category_name && (
              <p className="mt-1 flex items-center gap-1 text-sm text-gray-500">
                <Folder className="w-3.5 h-3.5" />
                {doc.category_name}
              </p>
            )}
          </div>
        </div>

        {/* Description */}
        {doc.description && (
          <div className="px-6 py-4 border-b border-gray-100">
            <p className="text-sm text-gray-600 leading-relaxed">{doc.description}</p>
          </div>
        )}

        {/* Metadata */}
        <div className="px-6 py-2">
          <dl>
            <InfoRow label="File name">
              <span className="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded">{doc.file_name}</span>
            </InfoRow>
            <InfoRow label="File size">{formatFileSize(doc.file_size)}</InfoRow>
            <InfoRow label="Last modified">
              <span className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-gray-400" />
                {formatDate(doc.last_modified)}
              </span>
            </InfoRow>
            <InfoRow label="Indexed">{formatDate(doc.indexed_at)}</InfoRow>
            {doc.allowed_groups.length > 0 && (
              <InfoRow label="Access groups">
                <span className="flex items-center gap-1.5 flex-wrap">
                  <Lock className="w-3.5 h-3.5 text-gray-400" />
                  {doc.allowed_groups.map((g) => (
                    <span key={g} className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full">
                      {g}
                    </span>
                  ))}
                </span>
              </InfoRow>
            )}
            {doc.tags.length > 0 && (
              <InfoRow label="Tags">
                <span className="flex items-center gap-1.5 flex-wrap">
                  <Tag className="w-3.5 h-3.5 text-gray-400" />
                  {doc.tags.map((t) => (
                    <span key={t} className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">
                      {t}
                    </span>
                  ))}
                </span>
              </InfoRow>
            )}
          </dl>
        </div>

        {/* Network path */}
        <div className="px-6 py-5 border-t border-gray-100 bg-gray-50">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <FileText className="w-3.5 h-3.5" />
            Network path
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-700 font-mono break-all">
              {doc.file_path}
            </code>
            <Button
              variant={copied ? 'secondary' : 'primary'}
              size="sm"
              onClick={copyPath}
              className="flex-shrink-0"
            >
              <Copy className="w-4 h-4" />
              {copied ? 'Copied!' : 'Copy'}
            </Button>
          </div>
          <p className="mt-2 text-xs text-gray-400">
            Paste this path into Windows Explorer (address bar) to open the file directly.
          </p>
        </div>
      </div>
    </div>
  )
}
