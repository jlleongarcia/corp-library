import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import type { SnippetSegment } from '../types'
import { cn, fileTypeBadgeClass } from '../lib/utils'
import { Button } from './ui'

export function FileTypeBadge({ ext, className }: { ext: string; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center justify-center min-w-[3rem] px-1.5 py-0.5 rounded text-[11px] font-semibold uppercase',
        fileTypeBadgeClass(ext),
        className,
      )}
    >
      {ext || 'file'}
    </span>
  )
}

/** Search snippet: matches are highlighted from the API's segments, never by parsing HTML. */
export function Snippet({ segments }: { segments: SnippetSegment[] }) {
  if (segments.length === 0) return null
  return (
    <p className="text-sm text-gray-600 leading-relaxed">
      {segments.map((s, i) => (s.hit ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>))}
    </p>
  )
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Older browsers, or the clipboard API refused: select-and-copy fallback.
    const area = document.createElement('textarea')
    area.value = text
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    area.remove()
    return ok
  }
}

/**
 * Browsers block file:// links from an https page, so the way to open a document
 * in place is to paste its network path into Explorer (or Office's Open dialog).
 */
export function CopyPathButton({ path, size = 'sm', label = 'Copy network path' }: {
  path: string; size?: 'sm' | 'md'; label?: string
}) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      variant="secondary"
      size={size}
      title={`Copy ${path} to paste into File Explorer`}
      onClick={async (e) => {
        e.preventDefault()
        e.stopPropagation()
        if (await copyText(path)) {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        }
      }}
    >
      {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
      {copied ? 'Copied' : label}
    </Button>
  )
}
