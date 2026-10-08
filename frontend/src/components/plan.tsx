import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Ban, Check, FolderTree, User } from 'lucide-react'
import type { PlanGuideEntry } from '../types'
import { CopyPathButton } from './library'

/** Lower-case, no accents: "Información" matches "informacion", as in search. */
export function fold(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/** Does every word typed appear somewhere in the entry (name, purpose, keywords...)? */
export function entryMatches(entry: PlanGuideEntry, query: string): boolean {
  const words = fold(query).split(/\s+/).filter(Boolean)
  if (words.length === 0) return true
  const text = fold([
    entry.path, entry.purpose, entry.belongs, entry.naming, entry.owner,
    ...entry.keywords, ...entry.examples, ...entry.extensions,
  ].join(' '))
  return words.every((w) => text.includes(w))
}

export const NAMING_HELP =
  'Checked against the file name without its extension, ignoring case and accents. ' +
  '* is any text, ? one character, {YYYY} a year, {YY} two digits, {MM} a month, {DD} a day, {N} a number.'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-gray-800 whitespace-pre-line">{children}</dd>
    </div>
  )
}

export function Chips({ items, mono }: { items: string[]; mono?: boolean }) {
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((k) => (
        <span key={k} className={`px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 text-xs ${mono ? 'font-mono' : ''}`}>{k}</span>
      ))}
    </span>
  )
}

/** Everything the plan says about one folder, as people read it. */
export function PlanDetails({ entry }: { entry: PlanGuideEntry }) {
  const hasNaming = entry.naming || entry.naming_pattern || entry.examples.length > 0
  return (
    <dl className="grid gap-3 sm:grid-cols-2">
      {entry.purpose && <div className="sm:col-span-2"><Field label="Purpose">{entry.purpose}</Field></div>}
      {entry.belongs && (
        <Field label="What goes here">
          <span className="flex gap-1.5"><Check className="w-4 h-4 mt-0.5 text-green-600 flex-shrink-0" />{entry.belongs}</span>
        </Field>
      )}
      {entry.not_belongs && (
        <Field label="What doesn't">
          <span className="flex gap-1.5"><Ban className="w-4 h-4 mt-0.5 text-red-600 flex-shrink-0" />{entry.not_belongs}</span>
        </Field>
      )}
      {hasNaming && (
        <Field label="How to name files">
          {entry.naming && <span className="block">{entry.naming}</span>}
          {entry.naming_pattern && (
            <span className="block mt-1">Pattern: <code className="font-mono text-xs bg-gray-100 rounded px-1">{entry.naming_pattern}</code></span>
          )}
          {entry.examples.length > 0 && (
            <span className="block mt-1">
              <span className="text-gray-500">For example: </span>
              <Chips items={entry.examples} mono />
            </span>
          )}
        </Field>
      )}
      {(entry.extensions.length > 0 || !entry.allow_files || entry.allow_subfolders) && (
        <Field label="Rules">
          {entry.extensions.length > 0 && <span className="block">File types: {entry.extensions.map((e) => `.${e}`).join(', ')}</span>}
          {!entry.allow_files && <span className="block">Don't save files directly here: use one of its subfolders.</span>}
          {entry.allow_subfolders && <span className="block">You may create subfolders (by project, year...).</span>}
        </Field>
      )}
      {entry.owner && (
        <Field label="Owner">
          <span className="flex items-center gap-1.5"><User className="w-4 h-4 text-gray-400" />{entry.owner}</span>
        </Field>
      )}
      {entry.keywords.length > 0 && <Field label="Keywords"><Chips items={entry.keywords} /></Field>}
    </dl>
  )
}

/** The folder's network path with a copy button, and a link to browse it if it exists. */
export function PlanEntryActions({ entry }: { entry: PlanGuideEntry }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {entry.folder_id && (
        <Link to={`/browse/${entry.folder_id}`} className="inline-flex items-center gap-1 text-sm text-blue-700 hover:underline">
          <FolderTree className="w-4 h-4" /> Browse
        </Link>
      )}
      <CopyPathButton path={entry.network_path} label="Copy folder path" />
    </div>
  )
}
