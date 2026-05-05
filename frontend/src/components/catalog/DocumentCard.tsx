import { Copy, ExternalLink, Tag, Calendar } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { fileTypeBadgeClass, formatDate } from '../../lib/utils'
import { cn } from '../../lib/utils'
import type { Document, SearchResult } from '../../types'

type CardDoc = Pick<
  Document | SearchResult,
  | 'id'
  | 'title'
  | 'file_name'
  | 'file_extension'
  | 'file_path'
  | 'category_name'
  | 'tags'
  | 'last_modified'
> & { highlight_title?: string | null; highlight_description?: string | null }

interface DocumentCardProps {
  doc: CardDoc
  className?: string
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
}

export default function DocumentCard({ doc, className }: DocumentCardProps) {
  const navigate = useNavigate()
  const ext = doc.file_extension?.toUpperCase() ?? 'FILE'

  return (
    <div
      className={cn(
        'bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md hover:border-blue-200 transition-all cursor-pointer group',
        className,
      )}
      onClick={() => navigate(`/documents/${doc.id}`)}
    >
      <div className="flex items-start gap-3">
        {/* File type badge */}
        <span
          className={cn(
            'flex-shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-lg text-xs font-bold',
            fileTypeBadgeClass(doc.file_extension),
          )}
        >
          {ext.length > 4 ? ext.slice(0, 4) : ext}
        </span>

        <div className="flex-1 min-w-0">
          {/* Title with optional search highlight */}
          {doc.highlight_title ? (
            <h3
              className="font-semibold text-gray-900 text-sm leading-snug group-hover:text-blue-700 transition-colors"
              dangerouslySetInnerHTML={{ __html: doc.highlight_title }}
            />
          ) : (
            <h3 className="font-semibold text-gray-900 text-sm leading-snug group-hover:text-blue-700 transition-colors truncate">
              {doc.title}
            </h3>
          )}

          {/* Description snippet */}
          {doc.highlight_description && (
            <p
              className="mt-0.5 text-xs text-gray-500 line-clamp-2"
              dangerouslySetInnerHTML={{ __html: doc.highlight_description }}
            />
          )}

          {/* Meta row */}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
            {doc.category_name && (
              <span className="flex items-center gap-1">
                <ExternalLink className="w-3 h-3" />
                {doc.category_name}
              </span>
            )}
            {doc.last_modified && (
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {formatDate(doc.last_modified)}
              </span>
            )}
          </div>

          {/* Tags */}
          {doc.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {doc.tags.slice(0, 5).map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 text-xs"
                >
                  <Tag className="w-2.5 h-2.5" />
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Copy path action */}
        <button
          title="Copy file path"
          onClick={(e) => {
            e.stopPropagation()
            copyToClipboard(doc.file_path)
          }}
          className="flex-shrink-0 p-1.5 rounded-lg text-gray-300 hover:text-blue-600 hover:bg-blue-50 transition-colors opacity-0 group-hover:opacity-100"
        >
          <Copy className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
