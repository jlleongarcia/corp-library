# Corp Library — Bug log

_Last updated: 2026-10-08_

Every bug found in the app, what we did about it, and whether the fix is in. New bugs get the next
`BUG-NNN` number and a row in the table; details go in a section below.

**Status**

| Marker | Meaning |
| --- | --- |
| ✅ | Fixed, and a regression test guards it (see *Check*) |
| 🟡 | Fixed in code, but only the real file server / AD can confirm it, or it waits on an IT answer |
| ⬜ | Open |

**Due**: when the fix must be in. *Now*, *Before first real scan* (end of phase 0: the worker, SMB and
LDAP all run against the real servers), *Before production*.

Run every check with `cd backend && uv run pytest` (SQLite) and `uv run scripts/pytest_postgres.py`
(PostgreSQL). CI runs both on every push.

---

## Summary

| ID | Severity | Bug | Due | Status | Check |
| --- | --- | --- | --- | --- | --- |
| [BUG-001](#bug-001) | Critical | `web` service runs the API image | Before production | ✅ | CI `.github/ci/smoke_test.sh` |
| [BUG-002](#bug-002) | Critical | Default `SECRET_KEY` lets anyone mint admin tokens | Before first real scan | ✅ | `test_hardening.py::test_unknown_or_forged_session_cookie_is_rejected` and 3 more |
| [BUG-003](#bug-003) | Critical | LDAPS doesn't validate the DC certificate | Before first real scan | 🟡 | `test_hardening.py::test_ldaps_always_validates_the_certificate` + first real sign-in |
| [BUG-004](#bug-004) | High | SMB session never re-authenticates after a dropped connection | Before first real scan | 🟡 | `test_hardening.py::test_smb_credentials_become_the_client_default` + real scan |
| [BUG-005](#bug-005) | High | Reparse-point files (dedup / cloud-tiered) silently skipped | Before first real scan | 🟡 | `test_scanner.py::test_reparse_folders_skipped_but_reparse_files_indexed` + IT answer |
| [BUG-006](#bug-006) | High | Share-level permissions ignored | Now (ask IT) | ⬜ | IT answer in ROADMAP open questions |
| [BUG-007](#bug-007) | High | File access taken from the folder's own ACEs | Now | ✅ | `test_acl.py::test_this_folder_only_lets_users_list_but_not_open_files` and 3 more; `test_search.py::test_search_shows_each_user_only_what_windows_lets_them_open` |
| [BUG-008](#bug-008) | High | Nightly scan skipped if the worker is busy at `SCAN_HOUR` | Before first real scan | ✅ | `test_hardening.py::test_nightly_scan_catches_up_after_a_long_job` |
| [BUG-009](#bug-009) | High | Transient LDAP error marks known users/groups "unknown" | Before first real scan | ✅ | `test_api.py::test_ldap_outage_keeps_known_principals` and 2 more |
| [BUG-010](#bug-010) | Medium | Login identity is the typed username; LDAP filter not escaped | Before first real scan | ✅ | `test_hardening.py::test_login_identity_is_the_account_ad_returns` and 2 more |
| [BUG-011](#bug-011) | Medium | nginx drops security headers on `index.html` | Before production | ✅ | CI `.github/ci/smoke_test.sh` |
| [BUG-012](#bug-012) | Medium | CSV exports open to formula injection in Excel | Before production | ✅ | `test_search.py::test_searches_views_and_downloads_are_audited` |
| [BUG-013](#bug-013) | Medium | Unreachable share = "partial"; unlisted folders reported "empty" | Before first real scan | ✅ | `test_scanner.py::test_unreachable_share_fails_the_run`, `test_api.py::test_hygiene_reports_unlisted_folders_not_empty` |
| [BUG-014](#bug-014) | Low | Scan ignore list is case-sensitive | Before production | ✅ | `test_hardening.py::test_scan_ignore_list_ignores_case` |
| [BUG-015](#bug-015) | Low | Negative `limit`/`offset` returns 500 | Before production | ✅ | `test_api.py::test_negative_limit_or_offset_is_a_422_not_a_500` |
| [BUG-016](#bug-016) | Low | Wrong password reloads the login page, erasing the error | Now | ✅ | Manual: wrong password shows the message (no frontend test suite yet) |
| [BUG-017](#bug-017) | Low | DEV_MODE guard only checks `LDAP_SERVER` | Before production | ✅ | `test_hardening.py::test_dev_mode_is_refused_outside_a_developer_pc` and 1 more |
| [BUG-018](#bug-018) | Low | Healthchecks may go through the corporate proxy | Before production | 🟡 | `api` turns healthy on the server |
| [BUG-019](#bug-019) | Low | Two workers would scan the same share concurrently | Before production | ⬜ | — |
| [BUG-020](#bug-020) | Low | Compose header says `up -d --build` but nothing builds | Before production | ✅ | Comment only |
| [BUG-021](#bug-021) | Medium | `-word` doesn't exclude other forms of the word | Before production | ✅ | `test_search.py::test_excluded_words_and_phrases` (PostgreSQL) |
| [BUG-022](#bug-022) | Low | Mixed `/` and `\` in paths of local shares on Linux (CI red) | Now | ✅ | `test_api.py::test_display_paths_keep_the_share_separator` |
| [BUG-023](#bug-023) | High | Text of a file stricter than its folder is shown to everyone who can read the folder | Before first real scan | ✅ | `test_search.py::test_file_stricter_than_its_folder_keeps_its_text_to_itself`, `::test_file_shared_in_a_folder_whose_files_are_closed` |
| [BUG-024](#bug-024) | High | A file that crashes or hangs the extractor stops content indexing for good | Before first real scan | ✅ | `test_extract_process.py` (4 tests + 1 on Linux), `test_search.py::test_file_that_killed_the_worker_is_not_read_again` |
| [BUG-025](#bug-025) | Medium | An edited name-only file (`.dwg`, `.zip`, …) is downloaded and marked "error" | Before first real scan | ✅ | `test_search.py::test_changed_name_only_file_is_not_read` |
| [BUG-026](#bug-026) | Medium | An index round overruns its 20 minutes and can cancel the nightly scan | Before first real scan | ✅ | `test_search.py::test_index_round_stops_at_its_deadline` |
| [BUG-027](#bug-027) | Low | Search slow on a big index (2–4 s for common words at 100k documents) | Before production | ✅ | `test_search.py::test_count_is_optional_and_capped`, `::test_name_matches_survive_when_too_many_documents_match` (PostgreSQL); `scripts/bench_search.py` |
| [BUG-028](#bug-028) | Low | Download/preview errors replace the app with raw JSON | Before production | ✅ | `test_search.py::test_browser_gets_a_page_not_json_when_a_file_cant_be_opened`; CI smoke test |
| [BUG-029](#bug-029) | Low | Sign-in form: no throttling (AD lockouts), `DOMAIN\user` rejected | Before production | 🟡 | `test_sso.py::test_repeated_wrong_passwords_stop_reaching_ad` and 2 more; values from IT |
| [BUG-030](#bug-030) | Low | Renaming a share left the old name in the search index | Before production | ✅ | `test_search.py::test_renamed_share_is_found_by_its_new_name` |
| [BUG-031](#bug-031) | Low | No Content-Security-Policy or HSTS | Before production | 🟡 | CI `.github/ci/smoke_test.sh` (✅ after its next green run) |
| [BUG-032](#bug-032) | Low | Download keeps the SMB file open if the browser disconnects early | Before production | ✅ | `test_search.py::test_download_handle_is_closed_even_if_never_read` |
| [BUG-033](#bug-033) | Medium | No privacy notice for sign-in data and the audit log (GDPR / LOPDGDD) | Before production | ⬜ | Draft notice in code (`test_privacy.py`); pending expert legal review |
| [BUG-034](#bug-034) | Medium | Google Fonts sends every user's IP address to Google | Before production | ✅ | CI `.github/ci/smoke_test.sh` ("index.html loads nothing from other sites") |
| [BUG-035](#bug-035) | Medium | Folder plan drawn as the wrong tree when names share a prefix ("Contratos" / "Contratos 2024") | Before production | ✅ | `test_plan.py::test_plan_lists_each_folder_before_its_subfolders` |
| [BUG-036](#bug-036) | Medium | Compliance lists show an arbitrary 200 problems, not the biggest; the CSV stops at 5,000 | Before production | ✅ | `test_plan.py::test_lists_keep_the_biggest_problems_and_the_csv_keeps_them_all` |
| [BUG-037](#bug-037) | Medium | A naming pattern with several `*` takes seconds per file (regex backtracking) | Before production | ✅ | `test_plan.py::test_naming_patterns_with_many_stars_stay_fast` |
| [BUG-038](#bug-038) | Low | Folders the scanner couldn't list make planned folders look empty or missing | Before production | ✅ | `test_plan.py::test_unlisted_folders_are_not_reported_empty_or_missing` |
| [BUG-039](#bug-039) | Low | "Correctly named" counts files that have no naming rule | Before production | ✅ | `test_plan.py::test_correctly_named_counts_only_files_under_a_naming_pattern` |
| [BUG-040](#bug-040) | Low | Compliance CSV is a 500 when the share's name has a character outside Latin-1 | Before production | ✅ | `test_plan.py::test_csv_download_name_may_hold_any_character` |
| [BUG-041](#bug-041) | Low | Browsing shows the guide of a folder above that the user can't list | Before production | ✅ | `test_plan.py::test_browse_hides_the_guide_of_a_folder_above_that_the_user_cannot_list` |
| [BUG-042](#bug-042) | Low | If the last scan of the night fails, no index, dedupe or progress snapshot follows | Before first real scan | ✅ | `test_plan.py::test_follow_up_jobs_are_queued_even_if_the_last_scan_fails` |

---

## Details

### BUG-001

**`web` service runs the API image.** `docker-compose.yml` used `corp-library-api:latest` for `web`. That
image runs uvicorn on 8000; Traefik routes to port 80, so every request would get a 502.

- **Fix:** `image: ghcr.io/jlleongarcia/corp-library-web:latest`.
- **Files:** `docker-compose.yml`
- **Status:** ✅ Fixed. The CI smoke test starts `docker-compose.yml` as is and reaches the UI through
  `web` (first green run on `7c58a7b`).

### BUG-002

**Default `SECRET_KEY` lets anyone mint admin tokens.** Tokens are signed with `SECRET_KEY`, and admin
rights come from the username inside the token. The code default and `.env.example`'s `change-me` are
public, as is the admin username.

- **Fix (phase 0):** `config.secret_key_problem()` rejected weak keys and `main.py` refused to start with one.
- **Fix (phase 1, replaces it):** JWTs are gone. A session is a random token in an HttpOnly cookie, looked
  up in the `sessions` table (only its SHA-256 is stored). Nothing is signed, so there is no key to leak,
  and sign-out deletes the row. `SECRET_KEY` is no longer read.
- **Files:** `backend/app/auth/sessions.py`, `backend/app/routers/auth.py`, `backend/app/config.py`, `.env.example`
- **Status:** ✅ Fixed.

### BUG-003

**LDAPS doesn't validate the DC certificate.** ldap3's `Server(use_ssl=True)` defaults to
`ssl.CERT_NONE`, so a man in the middle could read user and service-account passwords.

- **Fix:** `ldap_client.make_server()` (used by sign-in and the directory lookups) always sets
  `Tls(validate=CERT_REQUIRED, valid_names=[LDAP_SERVER])`. New setting `LDAP_CA_CERT_FILE` points to the
  internal CA (empty = system CAs); Compose mounts `./certs` read-only at `/certs` for `api` and `worker`.
  LDAP errors other than bad credentials are now logged at ERROR, so a certificate problem is visible.
- **Files:** `backend/app/auth/ldap_client.py`, `backend/app/services/directory.py`, `backend/app/config.py`,
  `docker-compose.yml`, `.env.example`, `docs/DEPLOYMENT.md`
- **Status:** 🟡 Fixed in code. Confirm with the first real sign-in: needs the CA file from IT, and
  `LDAP_SERVER` must be the name on the DC's certificate.

### BUG-004

**SMB session never re-authenticates after a dropped connection.** Credentials were passed once to
`smbclient.register_session`, guarded by a module-level set. After a dropped connection (or a DFS referral
to another server) smbclient opens a fresh session using `ClientConfig` defaults, which had no username,
so every later call failed until the worker restarted.

- **Fix:** `sources.configure_smb_client()` sets the scanner account as `smbclient.ClientConfig` defaults;
  called before every SMB operation (idempotent). The `_registered_servers` guard is gone.
- **Files:** `backend/app/services/sources.py`
- **Status:** 🟡 Fixed in code. Confirm during the first real scan (a network blip mid-scan should
  recover instead of failing every following folder).

### BUG-005

**Reparse-point files silently skipped.** The scanner skipped every entry with
`FILE_ATTRIBUTE_REPARSE_POINT`. On a file server, Data Deduplication and Azure File Sync cloud tiering
mark ordinary files that way, so they would have vanished from the inventory without an error.

- **Fix:** only *folders* that are reparse points (junctions, symlinks, DFS links) are skipped, since
  following them could loop or leave the share. They're counted in the new `scan_runs.folders_skipped`
  (migration `0002`), logged, and shown in **Scan activity**. Reparse-point files are indexed. The local
  dev source now reports links to folders as folders, so they're skipped too.
- **Files:** `backend/app/services/scanner.py`, `backend/app/services/sources.py`, `backend/app/models.py`,
  `backend/alembic/versions/0002_scan_visibility.py`, `frontend/src/pages/admin/ActivityTab.tsx`
- **Status:** 🟡 Fixed in code. Open IT question (ROADMAP): is Dedup / Azure File Sync / DFS used? If the
  shares are DFS paths, the namespace needs configuring (smbclient `domain_controller`).

### BUG-006

**Share-level permissions ignored.** Over SMB, access = share permissions ∩ NTFS. The scanner reads only
NTFS. A restrictive share permission would make phase 1 show files people can't open (breaks *fail
closed*).

- **Fix (pending IT):** if IT confirms shares are "Authenticated Users/Everyone: Full" at the share level,
  document the assumption and close. Otherwise read the share ACL (`NetShareGetInfo` level 502) and
  intersect.
- **Status:** ⬜ Open. Question added to ROADMAP *Open questions*.

### BUG-007

**File access taken from the folder's own ACEs.** A folder's DACL describes the folder ("can list it").
Files inherit only the ACEs marked *object inherit*, including inherit-only ones. With "Read, this folder
only" (a common way to let people browse a share root), the old logic would show everyone the files in
that folder.

- **Fix:** `acl.evaluate.file_aces()` / `can_read_files()` derive a file's DACL from its folder's ACEs
  (object-inherit only, order kept, CREATOR OWNER/GROUP never grant). ROADMAP notes that phase 1 must
  filter files with `can_read_files`. The permission grid still shows folder access, which is what it
  means.
- **Files:** `backend/app/acl/evaluate.py`, `docs/ROADMAP.md`
- **Status:** ✅ Fixed. Phase 1 search, browse and documents filter files with it (`services/access.py`).

### BUG-008

**Nightly scan skipped if the worker is busy at `SCAN_HOUR`.** The schedule was checked between jobs and
only when `now.hour == SCAN_HOUR`, so a job that ran across that hour cancelled the night's scan.

- **Fix:** `worker.maybe_schedule()` works with the most recent `SCAN_HOUR` slot and queues it if the
  worker frees up within `CATCH_UP` (4 h). Later than that it waits for the next night, to keep load off
  the file server during working hours. The "already queued since the slot" database check still
  prevents duplicates after a restart.
- **Files:** `backend/app/worker.py`
- **Status:** ✅ Fixed.

### BUG-009

**Transient LDAP error marks known users/groups "unknown".** A failed lookup set `kind = "unknown"` and
stamped `resolved_at`, so the group's members vanished from the permission grid for a day. A failure
while naming group members aborted the whole job, and big groups cost one LDAP query per member.

- **Fix:** a failed lookup or member expansion leaves the stored principal and members untouched and
  doesn't stamp `resolved_at` (retried next run); failures are counted in `stats["errors"]`. The LDAP
  connection uses `raise_exceptions=True`, so a dead connection raises instead of looking like "not
  found". Member names come back in the same paged search (no N+1) and are refreshed each expansion.
- **Files:** `backend/app/services/directory.py`
- **Status:** ✅ Fixed. Worth watching the worker log during the first real resolve job.

### BUG-010

**Login identity is the typed username; LDAP filter not escaped.** Sign-in bound as `typed@domain` then
used the typed text as the identity (and for the admin check), and put it unescaped into the search
filter.

- **Fix:** the username is escaped with `escape_filter_chars`; the identity is the `sAMAccountName` AD
  returns (lower-cased). Referrals are ignored; if the search doesn't find exactly one account, sign-in
  fails (fail closed).
- **Files:** `backend/app/auth/ldap_client.py`, `backend/app/routers/auth.py`
- **Status:** ✅ Fixed.

### BUG-011

**nginx drops security headers on `index.html`.** Any `add_header` in a `location` stops inheritance of
the server-level ones: `location /` loses `X-Frame-Options`, `nosniff` and `Referrer-Policy`.

- **Fix:** the headers live in `frontend/security-headers.conf`, included by the server and every
  location. `X-Frame-Options` is now `SAMEORIGIN` (the document page frames PDF previews).
- **Files:** `frontend/nginx.conf`, `frontend/security-headers.conf`, `frontend/Dockerfile`
- **Status:** ✅ Fixed. The CI smoke test checks the headers on every location (first green run on `7c58a7b`).

### BUG-012

**CSV formula injection.** Anyone can name a file `=HYPERLINK(...).docx`; exported to CSV and opened in
Excel, it's evaluated as a formula.

- **Fix:** `routers/reports.py::_cell` prefixes string cells starting with `= + - @`, tab or CR with `'`.
  It matters more now: the audit export contains search text typed by any user.
- **Files:** `backend/app/routers/reports.py`
- **Status:** ✅ Fixed.

### BUG-013

**Unreachable share reported "partial"; unlisted folders reported "empty".** A share whose root couldn't
be listed (wrong path, credentials, server down) ended as "partial". Folders that couldn't be listed had
no children in the database and showed up as *empty* in the hygiene report.

- **Fix:** new `folders.list_error` (migration `0002`), set when listing fails and cleared when it
  succeeds. A run whose root can't be listed is `failed`. Hygiene excludes unlisted folders from *empty*
  and lists them separately (UI card + CSV rows "could not list").
- **Files:** `backend/app/services/scanner.py`, `backend/app/services/reports.py`,
  `backend/app/routers/reports.py`, `backend/app/models.py`, `backend/alembic/versions/0002_scan_visibility.py`,
  `frontend/src/pages/admin/HygieneTab.tsx`, `frontend/src/types/index.ts`
- **Status:** ✅ Fixed.

### BUG-014

**Scan ignore list is case-sensitive.** `THUMBS.DB` or `Desktop.ini` variants get indexed; Windows names
are case-insensitive.

- **Fix:** `scanner._ignored` compares with `casefold()`.
- **Files:** `backend/app/services/scanner.py`
- **Status:** ✅ Fixed.

### BUG-015

**Negative `limit`/`offset` returns 500.** PostgreSQL rejects negative `LIMIT`/`OFFSET`.

- **Fix:** `ge=1` on every `limit`, `ge=0` on every `offset` (admin, reports, search, audit): FastAPI answers 422.
- **Files:** `backend/app/routers/admin.py`, `backend/app/routers/reports.py`, `backend/app/routers/library.py`
- **Status:** ✅ Fixed.

### BUG-016

**Wrong password reloads the login page.** The axios 401 handler redirected to `/login` even for the
login request itself, erasing the form's error message.

- **Fix:** the handler ignores 401s from `/auth/login`.
- **Files:** `frontend/src/lib/api.ts`
- **Status:** ✅ Fixed (type-checked; no frontend test suite yet, checked by reading the flow).

### BUG-017

**DEV_MODE guard only checks `LDAP_SERVER`.** With `DEV_MODE=true` and LDAP empty in production, anyone
signs in as admin with the dev password.

- **Fix:** `config.dev_mode_problem()` refuses DEV_MODE when `LDAP_SERVER` or `KERBEROS_KEYTAB` is set,
  or the database isn't on localhost (production's is always the `db` container). `main.py` won't start
  the API, and the login handler checks again. The dev identity takes no password (`DEV_PASSWORD` is
  gone) and gets fake groups from `DEV_GROUPS`. (`APP_HOST` wasn't used as the signal: a developer's
  `.env` copied from the example has it set.)
- **Files:** `backend/app/config.py`, `backend/app/main.py`, `backend/app/routers/auth.py`, `backend/app/auth/dev.py`
- **Status:** ✅ Fixed.

### BUG-018

**Healthchecks may go through the corporate proxy.** If Docker injects `HTTP_PROXY` into containers,
`urllib` in the API healthcheck would send `http://localhost:8000` to the proxy, keeping `api` unhealthy
and `worker` from starting.

- **Fix:** `NO_PROXY` / `no_proxy` = `localhost,127.0.0.1,api,db` in the backend environment.
- **Files:** `docker-compose.yml`
- **Status:** 🟡 Fixed in code. Confirm `api` becomes healthy on the server.

### BUG-019

**Two workers would scan the same share concurrently.** Nothing locks a share; two scans would clash on
the unique constraints.

- **Fix (to apply):** keep one worker (comment in Compose), or take a `pg_advisory_xact_lock(share_id)`
  per scan.
- **Status:** ⬜ Open.

### BUG-020

**Compose header says `docker compose up -d --build`,** but images come from ghcr.io; nothing builds.

- **Fix:** the comment says `docker compose pull && docker compose up -d`.
- **Status:** ✅ Fixed.

### BUG-021

**`-word` doesn't exclude other forms of the word.** Each query runs three ways (as typed, Spanish
stems, English stems) OR-ed together, and the exclusion was inside each one. Document text is stored
as stems only, so for `contrato -informes` the "as typed" query never saw `informes` in a document
saying "informes" and let it through.

- **Fix:** `parse_query` takes `-word` and `-"phrase"` out of the query; `search.py` rejects a document
  when any of the three forms of each exclusion matches. `-INF-2023` excludes the phrase "inf 2023".
- **Files:** `backend/app/services/text.py`, `backend/app/services/search.py`
- **Status:** ✅ Fixed.

### BUG-022

**CI red since phase 1: mixed separators in paths of local shares.** `display_path` always joined with
`\`, right for production's UNC shares, but a local share on Linux showed as `/srv/share\Finance\a.docx`.
`test_results_carry_snippet_and_network_path` failed on the Linux runner; Windows hid it.

- **Fix:** `display_path` keeps `/` for POSIX share paths (`/...`, not `//server`); report tests
  compare with `os.sep`.
- **Files:** `backend/app/services/reports.py`, `backend/tests/test_api.py`, `backend/tests/test_search.py`
- **Status:** ✅ Fixed.

### BUG-023

**Text of a file stricter than its folder is shown to everyone who can read the folder.** Search, the
document page and its 5,000-character text excerpt only checked the folder's permissions; only
open/download re-read the file's own ACL. A sheet locked down inside a widely readable folder exposed
its name and most of its text, and phase 3 would have handed that text to the assistant.

- **Fix:** the content pass reads the file's security descriptor before its text (the file is being
  opened anyway; if the ACL can't be read, the text isn't stored). A file with explicit ACEs or
  inheritance disabled gets `files.acl_id` (migration `0004`): its explicit ACEs only, plus
  `is_protected`. `access.file_access()` evaluates each (file ACL, folder ACL) pair as Windows does,
  explicit ACEs first, then the folder's inheritable ones unless protected, and every query uses it
  (search, share filter, browse, document page). A failed re-read keeps the last known ACL. Files
  indexed by name only keep following their folder (their ACL isn't read: no file is opened for them);
  open/download still check live. `.corplib-acl.json` gained per-file rules to test it.
- **Files:** `backend/app/services/access.py`, `indexer.py`, `scanner.py` (`AclStore.file_acl_id`),
  `search.py`, `library.py`, `devacl.py`, `backend/app/models.py`, `backend/alembic/versions/0004_file_acls_and_title_vectors.py`
- **Status:** ✅ Fixed.

### BUG-024

**A file that crashes or hangs the extractor stops content indexing for good.** The content pass
committed every 20 files and always started with the lowest pending id. A native crash in pdfium rolled
the batch back and the next run picked the same file again; a hang blocked the worker forever.

- **Fix:** extraction runs in a long-lived child process (`extract_process.py`); a crash, a run past
  `EXTRACT_TIMEOUT_SECONDS` or (Linux) more memory than `EXTRACT_MEMORY_MB` fails that file only and the
  child is replaced. Each file is marked `extracting` and committed before it is read; a file left that
  way by a dead worker becomes `error` on the next run instead of being read again.
- **Files:** `backend/app/services/extract_process.py`, `indexer.py`, `backend/app/config.py`
- **Status:** ✅ Fixed. The memory limit test runs on Linux (CI) only.

### BUG-025

**An edited name-only file is downloaded and marked "error".** The scanner set every changed document
back to `pending`, including types that are only indexed by name; the content pass then read up to
50 MB of the file and failed ("not a valid Office file", "no extractor for .zip").

- **Fix:** a changed file gets the status a new file would (`extract.initial_status`); the content pass
  also refuses to read a type it can't extract.
- **Files:** `backend/app/services/scanner.py`, `extract.py`, `indexer.py`
- **Status:** ✅ Fixed.

### BUG-026

**An index round overruns its 20 minutes and can cancel the nightly scan.** The deadline was checked
once per batch of 20 files; 20 scanned PDFs can take hours. A round running past `SCAN_HOUR` + 4 h
skips that night's scan (BUG-008 by another route).

- **Fix:** the deadline is checked after every file (each is committed on its own).
- **Files:** `backend/app/services/indexer.py`
- **Status:** ✅ Fixed.

### BUG-027

**Search was slow on a big index.** Measured with the new `scripts/bench_search.py` (200k files, 100k
readable by the user): a common word sorted by relevance took 2.2 s, two common words 4.3 s, linear in
the number of matches (ranking reads every match's vector), and every search counted all matches, the
home page's "recently modified" list included.

- **Fix:** the home page asks for no count (`count=false`); counts stop at 1,000 ("1,000+"; the UI shows
  50 pages); the rank is only computed when it orders the results; with more than 1,000 matches,
  relevance ranks the 1,000 newest whose name or folder matches (new `documents.title_vector`, small,
  with its own index) plus the 1,000 newest matching anywhere. Now every benchmark query is under
  350 ms (common word: 110 ms; two common words: 135 ms).
- **Files:** `backend/app/services/search.py`, `indexer.py`, `backend/app/routers/library.py`,
  `backend/app/schemas.py`, `backend/scripts/bench_search.py`, `frontend/src/pages/SearchPage.tsx`
- **Status:** ✅ Fixed. Re-run the benchmark once the real index exists (real documents are longer).

### BUG-028

**Download/preview errors replace the app with raw JSON.** They are plain links, so a 403/404/503
showed `{"detail": ...}` in the tab.

- **Fix:** when the browser itself opens a download/preview link (`Sec-Fetch-Dest: document/iframe`),
  errors come back as a short HTML page with a link back to the document (or to sign-in on 401). The
  app's own requests still get JSON.
- **Files:** `backend/app/routers/library.py`, `backend/app/main.py`, `.github/ci/smoke_test.sh`
- **Status:** ✅ Fixed.

### BUG-029

**Sign-in form: no throttling, `DOMAIN\user` rejected.** Anyone could lock a colleague's AD account out
by typing wrong passwords; `DOMAIN\alice` and `alice@domain` failed because `@LDAP_DOMAIN` was always
appended.

- **Fix:** after `LOGIN_MAX_FAILURES` (3) wrong passwords within `LOGIN_WINDOW_MINUTES` (30) the account
  is refused with 429 *without asking AD*, so the app alone can't reach AD's lockout threshold
  (recorded as `sign_in_failed` / `throttled`). `DOMAIN\alice` and `alice@<LDAP_DOMAIN>` sign in as `alice`.
- **Files:** `backend/app/auth/throttle.py`, `backend/app/routers/auth.py`, `backend/app/config.py`
- **Status:** 🟡 Fixed in code. Set the two values from the domain's lockout policy (ask IT).

### BUG-030

**Renaming a share left the old name in the search index** until each file changed.

- **Fix:** a rename queues an `index` job with `rebuild_share`, which replaces only the path part
  (weight B) of that share's vectors, folder by folder, without tokenising the text again.
- **Files:** `backend/app/services/indexer.py`, `backend/app/routers/admin.py`, `backend/app/worker.py`
- **Status:** ✅ Fixed.

### BUG-031

**No Content-Security-Policy or HSTS.** React escapes everything, so these are a second line of defence.

- **Fix:** the UI gets a strict CSP (`'self'` only: no inline script, no other sites). Not on API
  responses: a PDF preview served with it wouldn't render. HSTS (1 year, no subdomains) on everything.
- **Files:** `frontend/nginx.conf`, `frontend/security-headers.conf`, `.github/ci/smoke_test.sh`
- **Status:** 🟡 Fixed in code. ✅ after the smoke test's next green run.

### BUG-032

**Download kept the SMB file open if the browser disconnected before the first chunk.** The handle was
closed by the generator, which never runs in that case.

- **Fix:** `open_stream` also returns a close function, run by the response when it ends however it ends
  (and if recording the audit event fails).
- **Files:** `backend/app/services/library.py`, `backend/app/routers/library.py`
- **Status:** ✅ Fixed.

### BUG-033

**No privacy notice.** Sign-ins, searches (with the words typed), views and downloads are logged with
the user's name and IP for a year. Staff must be informed beforehand (GDPR arts. 13 and 14, LOPDGDD
arts. 11 and 87, TREBEP art. 14.j bis, Estatuto de los Trabajadores art. 20.3). Why, and the legal
analysis for a Spanish public institution: [docs/PRIVACY.md](PRIVACY.md).

- **Fix:** first layer (LOPDGDD art. 11) at the bottom of every page and on the sign-in page; full notice
  at `/privacy`, Spanish (authoritative) and English, public. Written for a public institution: bases
  6.1.e and 6.1.c (no legitimate interest), the log grounded on the ENS (RD 311/2022), mandatory DPO,
  link to the published record of processing, configurable supervisory authority (AEPD or regional).
  Institution details come from `PRIVACY_*` in `.env` (shown as `[pendiente: …]` until set; the api warns
  at startup), retention periods from the settings the code applies. To make the notice true: reading the
  audit log is itself logged (`audit_read`), and accounts unused for `AUDIT_RETENTION_DAYS` are deleted.
- **Files:** `frontend/src/pages/PrivacyPage.tsx`, `frontend/src/components/privacy.tsx`,
  `backend/app/routers/privacy.py`, `backend/app/services/audit.py`, `backend/app/routers/reports.py`,
  `backend/app/worker.py`, `.env.example`, `docs/PRIVACY.md`
- **Status:** ⬜ Open: the notice is a **draft**. Its wording and legal analysis are pending assessment by
  experienced people (the DPO and the institution's legal service). Close it only after that review and
  the go-live checklist in `docs/PRIVACY.md` (record of processing, ENS scope, DPIA assessment, staff
  representatives, `PRIVACY_*`).

### BUG-034

**Google Fonts sent every user's IP address to Google.** `index.html` loaded Inter from
`fonts.googleapis.com`: personal data sent to a third party (in the US) on every page load, against the
"nothing leaves the network" promise (cf. LG München I, 3 O 17493/20, 20 January 2022). It also failed
on PCs without internet access.

- **Fix:** the font is bundled (`@fontsource-variable/inter`); `index.html` references no other site,
  which the smoke test checks.
- **Files:** `frontend/index.html`, `frontend/src/main.tsx`, `frontend/tailwind.config.js`, `frontend/package.json`
- **Status:** ✅ Fixed.

### BUG-035

**Folder plan drawn as the wrong tree.** Entries were sorted by path, and `" "`, `-` and `.` sort before `/`:
"Contratos 2024" came between "Contratos" and "Contratos/2024", so the editor and the guide (which indent
by depth) showed 2024 under "Contratos 2024". PostgreSQL's collation ignores `/` and spaces, which mixes
them further. Spanish folder names with spaces made this certain on the real plan.

- **Fix:** `plan.entries()` sorts by the path's parts (`tree_order`), in Python, the same on both databases.
  The compliance lists use the same order.
- **Files:** `backend/app/services/plan.py`
- **Status:** ✅ Fixed.

### BUG-036

**Compliance lists showed an arbitrary 200 problems.** `_Capped` kept the first `limit` items *found*
(database order) and only sorted those, so "Outside the plan" and "Overgrown", sorted by files, could miss
the biggest folders. The CSV export asked for `limit=5000`, while the UI said "export for all".

- **Fix:** each list keeps the first `limit` items in its own order (biggest first; files and folders by
  path) with a bounded heap. The CSV export has no limit.
- **Files:** `backend/app/services/plan.py`, `backend/app/routers/reports.py`, `frontend/src/pages/admin/ComplianceTab.tsx`
- **Status:** ✅ Fixed.

### BUG-037

**Naming patterns with several `*` backtracked exponentially.** Each `*` became `.*`; for a name that
doesn't match, the regex tries every way of splitting it. `* * * * * x` took 1 s on a 240-character name
with 5 stars, 22 s with 6. The compliance job checks every file under the pattern, so one such pattern
could keep the worker busy for hours (and the API request for the report time out).

- **Fix:** the parts between stars are matched left to right, each at its earliest place, inside an atomic
  group (`(?>.*?part)`): the classic glob algorithm, linear. `{N}` is lazy so a part ends as early as it can.
  Same answers as before on 300,000 random pattern/name pairs.
- **Files:** `backend/app/services/plan.py`
- **Status:** ✅ Fixed.

### BUG-038

**Folders the scanner couldn't list made planned folders look empty or missing.** Only the folder's own
`list_error` was checked (BUG-013's rule): a planned folder whose subfolder couldn't be listed was
"empty", and a planned folder inside one that couldn't be listed was "not created yet".

- **Fix:** a folder with an unlisted folder anywhere below it is never "empty"; a planned folder is not
  "missing" when the folder that would hold it couldn't be listed.
- **Files:** `backend/app/services/plan.py`
- **Status:** ✅ Fixed.

### BUG-039

**"Correctly named" counted files without a naming rule.** `files_checked` counted every file under a
naming *or* file-type rule, and the percentage was `(checked − misnamed) / checked`. A share with 1,000
files under type-only rules and 100 under a pattern, half misnamed, showed 95 % instead of 50 %.

- **Fix:** `files_checked` counts files under a naming pattern only (column meaning changed, no migration:
  no real snapshots exist yet). Wrong types stay a count of their own.
- **Files:** `backend/app/services/plan.py`, `backend/app/models.py`
- **Status:** ✅ Fixed.

### BUG-040

**Compliance CSV was a 500 for some share names.** The file name (`compliance-<share>.csv`) went into
`Content-Disposition` as is: headers are Latin-1, so a `€` raised, and a `"` broke the header.

- **Fix:** `_attachment()` sends an ASCII fallback plus the real name as `filename*=UTF-8''…` (RFC 6266),
  for every CSV export.
- **Files:** `backend/app/routers/reports.py`
- **Status:** ✅ Fixed.

### BUG-041

**Browsing showed the guide of a folder above that the user can't list.** For a folder that isn't
planned itself, the browse page shows the entry it falls under (free) or where its files belong (outside).
That entry is an ancestor folder, which Windows may hide from the user (they reach the folder by traverse
rights). The guide hides it; browsing showed its purpose, owner and keywords, and linked to a guide entry
that wasn't there.

- **Fix:** the entry is only returned if the user can list that ancestor; otherwise the panel shows the
  warning without a link (outside) or nothing (free).
- **Files:** `backend/app/services/library.py`, `backend/app/services/plan.py`
- **Status:** ✅ Fixed.

### BUG-042

**If the last scan of the night failed, nothing followed it.** The worker queued principal resolution,
indexing, dedupe and (from phase 2) the progress snapshot after the last scan of a batch, but only if
that scan succeeded. One unreachable share scanned last meant a night without them, and a gap in the
refactor chart.

- **Fix:** the follow-up jobs are queued before a failed scan raises.
- **Files:** `backend/app/worker.py`
- **Status:** ✅ Fixed.

---

## Adding a bug

1. Next free ID; add a row to the summary table (status ⬜).
2. Add a `### BUG-NNN` section: what goes wrong and when, the fix, files touched.
3. When fixed, add a regression test where possible, put its name in *Check*, and switch to ✅
   (or 🟡 if only the real environment can confirm it).
