// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
  username: string
  display_name: string | null
  email: string | null
  is_admin: boolean
}

// ── Shares and jobs ───────────────────────────────────────────────────────────

export interface Share {
  id: number
  name: string
  path: string
  enabled: boolean
  created_at: string
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed'

export interface Job {
  id: number
  kind: 'scan' | 'resolve_principals' | 'dedupe'
  payload: Record<string, unknown>
  status: JobStatus
  requested_by: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  error: string | null
}

export interface ScanRun {
  id: number
  share_id: number
  started_at: string
  finished_at: string | null
  status: 'running' | 'success' | 'partial' | 'failed'
  folders_seen: number
  files_seen: number
  files_added: number
  files_updated: number
  files_removed: number
  error_count: number
  error_sample: string | null
}

// ── Reports ───────────────────────────────────────────────────────────────────

export interface ShareSummary {
  share_id: number
  share: string
  path: string
  enabled: boolean
  files: number
  bytes: number
  folders: number
  last_scan_status: ScanRun['status'] | null
  last_scan_finished: string | null
}

export interface SummaryReport {
  shares: ShareSummary[]
  by_extension: { extension: string; files: number; bytes: number }[]
  by_age: { bucket: string; files: number; bytes: number }[]
}

export interface DuplicateGroup {
  size: number
  copies: number
  wasted_bytes: number
  confidence: 'exact' | 'probable'
  files: { path: string; mtime: string | null }[]
}

export interface DuplicatesReport {
  total_groups: number
  total_wasted_bytes: number
  groups: DuplicateGroup[]
}

export interface StaleFolder {
  folder: string
  stale_files: number
  stale_bytes: number
  newest_stale: string | null
}

export interface HygieneReport {
  long_paths: { limit: number; count: number; items: { path: string; length: number }[] }
  deep_folders: { limit: number; count: number; items: { path: string; depth: number }[] }
  empty_folders: { count: number; items: { path: string }[] }
}

export type AccessLevel = 'full' | 'modify' | 'write' | 'read' | 'none'

export interface PrincipalRef {
  sid: string | null
  name: string
  display_name: string | null
  kind: 'user' | 'group' | 'computer' | 'wellknown' | 'unknown' | 'everyone'
}

export interface PermissionGrid {
  columns: { folder_id: number; path: string }[]
  rows: (PrincipalRef & { cells: Record<string, AccessLevel> })[]
}

export interface AclException {
  folder_id: number
  path: string
  is_share_root: boolean
  inheritance_disabled: boolean
  null_dacl: boolean
  acl_error: string | null
  entries: (PrincipalRef & { type: 'allow' | 'deny'; level: AccessLevel; inherited: boolean })[]
}
