// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
  username: string
  display_name: string | null
  email: string | null
  is_admin: boolean
}

/** The facts the privacy notice quotes (GET /privacy). */
export interface PrivacyInfo {
  controller: string
  controller_id: string
  controller_address: string
  contact: string
  dpo: string
  /** entry in the public record of processing activities (LOPDGDD art. 31.2) */
  record_url: string
  /** supervisory authority for complaints: the AEPD or a regional one */
  authority_name: string
  authority_url: string
  audit_retention_days: number
  backup_keep_days: number
  session_days: number
  groups_refresh_hours: number
  /** .env settings still empty: the notice shows them as pending */
  missing: string[]
}

export interface AuthConfig {
  app_name: string
  sso_enabled: boolean
  dev_mode: boolean
}

// ── Search, browse, documents ─────────────────────────────────────────────────

export interface SnippetSegment {
  text: string
  hit: boolean
}

export interface SearchResult {
  file_id: number
  name: string
  extension: string
  size: number
  mtime: string | null
  share_id: number
  share: string
  folder_id: number
  folder_path: string
  path: string
  snippet: SnippetSegment[]
}

export interface SearchResponse {
  /** null when not asked for (count=false); at most 1,000, see total_capped */
  total: number | null
  /** more matches than `total` */
  total_capped: boolean
  results: SearchResult[]
}

export interface Option {
  key: string
  label: string
}

export interface SearchFilters {
  shares: Option[]
  types: Option[]
}

export interface BrowseShare {
  id: number
  name: string
  path: string
  root_folder_id: number
}

export interface BrowseResponse {
  folder: { id: number; name: string; share_id: number; share: string; path: string }
  breadcrumbs: { folder_id: number | null; name: string }[]
  folders: { id: number; name: string; mtime: string | null }[]
  files: { file_id: number; name: string; extension: string; size: number; mtime: string | null }[]
  files_hidden: boolean
  files_truncated: boolean
  /** null: the share has no folder plan */
  plan: FolderPlacement | null
}

export type IndexStatus =
  | 'pending' | 'extracting' | 'text' | 'ocr' | 'empty' | 'metadata' | 'too_large' | 'ocr_unavailable' | 'error'

export interface DocumentDetail {
  file_id: number
  name: string
  extension: string
  size: number
  mtime: string | null
  ctime: string | null
  share_id: number
  share: string
  folder_id: number
  folder_path: string
  path: string
  index_status: IndexStatus | null
  preview: 'pdf' | 'image' | null
  text_excerpt: string | null
  text_truncated: boolean
}

// ── Audit ─────────────────────────────────────────────────────────────────────

export interface AuditEvent {
  id: number
  at: string
  username: string | null
  action: 'sign_in' | 'sign_in_failed' | 'sign_out' | 'search' | 'view' | 'preview' | 'download' | 'denied'
    | 'audit_read'
  file_id: number | null
  path: string | null
  detail: Record<string, unknown>
  client_ip: string | null
}

export interface AuditLog {
  total: number
  events: AuditEvent[]
}

export interface IndexStatusReport {
  counts: Partial<Record<IndexStatus | 'not_indexed', number>>
  ocr_available: boolean
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
  kind: 'scan' | 'resolve_principals' | 'dedupe' | 'index' | 'compliance'
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
  folders_skipped: number
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
  unlisted_folders: { count: number; items: { path: string; error: string }[] }
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

// ── Folder plan ───────────────────────────────────────────────────────────────

export interface PlanGuideEntry {
  id: number
  share_id: number
  share: string
  /** relative to the share, "/"-separated, "" for its root */
  path: string
  name: string
  depth: number
  network_path: string
  purpose: string
  belongs: string
  not_belongs: string
  owner: string
  naming: string
  naming_pattern: string | null
  examples: string[]
  extensions: string[]
  keywords: string[]
  allow_files: boolean
  allow_subfolders: boolean
  /** its folder, when it exists and the user can browse it */
  folder_id: number | null
}

export interface PlanEntryAdmin extends PlanGuideEntry {
  max_files: number | null
  /** the folder is on the share (as of the last scan) */
  exists: boolean
  /** examples its own rules would reject */
  example_problems: string[]
  updated_at: string
  updated_by: string | null
}

export interface PlanGuideShare {
  share_id: number
  share: string
  path: string
  entries: PlanGuideEntry[]
}

export interface FolderPlacement {
  /** free: a subfolder its plan entry allows without listing it */
  status: 'planned' | 'free' | 'outside'
  entry: PlanGuideEntry | null
}

export interface ComplianceTotals {
  files_total: number
  files_in_plan: number
  /** in the plan and under a naming or file-type rule */
  files_checked: number
  files_misnamed: number
  files_wrong_type: number
  folders_planned: number
  folders_missing: number
  folders_empty: number
  folders_overgrown: number
}

interface Capped<T> {
  count: number
  items: T[]
}

export interface ComplianceReport {
  share_id: number
  share: string
  totals: ComplianceTotals
  outside: Capped<{
    path: string; folder_id: number; files: number; reason: 'not_in_plan' | 'no_files_here'
    plan_id: number | null; plan_path: string | null
  }>
  misnamed: Capped<{ path: string; pattern: string; plan_id: number; plan_path: string }>
  wrong_type: Capped<{ path: string; extension: string; allowed: string[]; plan_id: number; plan_path: string }>
  missing: Capped<{ plan_id: number; path: string }>
  empty: Capped<{ plan_id: number; path: string }>
  overgrown: Capped<{ path: string; folder_id: number; files: number; limit: number }>
}

export interface ComplianceSnapshot extends ComplianceTotals {
  day: string
  taken_at: string
}

export interface ComplianceProgress {
  share_id: number
  share: string
  snapshots: ComplianceSnapshot[]
}
