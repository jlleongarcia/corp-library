// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
  username: string;
  display_name: string | null;
  email: string | null;
  is_admin: boolean;
  ad_groups: string[];
}

// ── Catalog ───────────────────────────────────────────────────────────────────

export interface Category {
  id: number;
  name: string;
  description: string | null;
  icon: string;
  color: string;
  parent_id: number | null;
  path: string | null;
  sort_order: number;
  auto_generated: boolean;
  document_count: number;
  children_count: number;
  children?: Category[];
}

// ── Documents ─────────────────────────────────────────────────────────────────

export interface Document {
  id: number;
  title: string;
  description: string | null;
  file_path: string;
  file_name: string;
  file_extension: string | null;
  file_size: number | null;
  category_id: number | null;
  category_name: string | null;
  category_path: string | null;
  last_modified: string | null;
  indexed_at: string;
  tags: string[];
  is_active: boolean;
}

export interface DocumentDetail extends Document {
  allowed_groups: string[];
}

// ── Search ────────────────────────────────────────────────────────────────────

export interface SearchResult {
  id: number;
  title: string;
  description: string | null;
  file_path: string;
  file_name: string;
  file_extension: string | null;
  category_name: string | null;
  category_id: number | null;
  tags: string[];
  last_modified: string | null;
  indexed_at: string;
  highlight_title: string | null;
  highlight_description: string | null;
}

export interface SearchResponse {
  query: string;
  total: number;
  results: SearchResult[];
  page: number;
  page_size: number;
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export interface ScanConfig {
  id: number;
  name: string;
  root_path: string;
  root_category_id: number | null;
  allowed_groups: string[];
  max_depth: number;
  file_extensions: string[] | null;
  is_active: boolean;
  create_subcategories: boolean;
  last_scan: string | null;
  scan_status: string;
  scan_error: string | null;
  documents_found: number;
  created_at: string;
}

export interface SystemStats {
  total_documents: number;
  total_categories: number;
  total_scan_configs: number;
  total_users: number;
  last_scan: string | null;
}
