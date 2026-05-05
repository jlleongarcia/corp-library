import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatFileSize(bytes: number | null): string {
  if (!bytes) return '—'
  if (bytes < 1_024) return `${bytes} B`
  if (bytes < 1_048_576) return `${(bytes / 1_024).toFixed(1)} KB`
  if (bytes < 1_073_741_824) return `${(bytes / 1_048_576).toFixed(1)} MB`
  return `${(bytes / 1_073_741_824).toFixed(1)} GB`
}

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

/** Tailwind classes for the file-type badge pill */
export function fileTypeBadgeClass(ext: string | null | undefined): string {
  switch (ext?.toLowerCase()) {
    case 'pdf':               return 'bg-red-100 text-red-700'
    case 'docx': case 'doc': return 'bg-blue-100 text-blue-700'
    case 'xlsx': case 'xls': return 'bg-green-100 text-green-700'
    case 'pptx': case 'ppt': return 'bg-orange-100 text-orange-700'
    case 'zip':
    case 'rar':
    case '7z':               return 'bg-gray-100 text-gray-600'
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':              return 'bg-purple-100 text-purple-700'
    case 'mp4':
    case 'avi':
    case 'mov':              return 'bg-pink-100 text-pink-700'
    case 'txt': case 'csv': return 'bg-teal-100 text-teal-700'
    default:                 return 'bg-gray-100 text-gray-600'
  }
}
