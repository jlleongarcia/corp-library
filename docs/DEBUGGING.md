# Corp Library — Bug log

_Last updated: 2026-10-07_

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
| [BUG-001](#bug-001) | Critical | `web` service runs the API image | Before production | 🟡 | CI `.github/ci/smoke_test.sh` (✅ after its first green run) |
| [BUG-002](#bug-002) | Critical | Default `SECRET_KEY` lets anyone mint admin tokens | Before first real scan | ✅ | `test_hardening.py::test_unknown_or_forged_session_cookie_is_rejected` and 3 more |
| [BUG-003](#bug-003) | Critical | LDAPS doesn't validate the DC certificate | Before first real scan | 🟡 | `test_hardening.py::test_ldaps_always_validates_the_certificate` + first real sign-in |
| [BUG-004](#bug-004) | High | SMB session never re-authenticates after a dropped connection | Before first real scan | 🟡 | `test_hardening.py::test_smb_credentials_become_the_client_default` + real scan |
| [BUG-005](#bug-005) | High | Reparse-point files (dedup / cloud-tiered) silently skipped | Before first real scan | 🟡 | `test_scanner.py::test_reparse_folders_skipped_but_reparse_files_indexed` + IT answer |
| [BUG-006](#bug-006) | High | Share-level permissions ignored | Now (ask IT) | ⬜ | IT answer in ROADMAP open questions |
| [BUG-007](#bug-007) | High | File access taken from the folder's own ACEs | Now | ✅ | `test_acl.py::test_this_folder_only_lets_users_list_but_not_open_files` and 3 more; `test_search.py::test_search_shows_each_user_only_what_windows_lets_them_open` |
| [BUG-008](#bug-008) | High | Nightly scan skipped if the worker is busy at `SCAN_HOUR` | Before first real scan | ✅ | `test_hardening.py::test_nightly_scan_catches_up_after_a_long_job` |
| [BUG-009](#bug-009) | High | Transient LDAP error marks known users/groups "unknown" | Before first real scan | ✅ | `test_api.py::test_ldap_outage_keeps_known_principals` and 2 more |
| [BUG-010](#bug-010) | Medium | Login identity is the typed username; LDAP filter not escaped | Before first real scan | ✅ | `test_hardening.py::test_login_identity_is_the_account_ad_returns` and 2 more |
| [BUG-011](#bug-011) | Medium | nginx drops security headers on `index.html` | Before production | 🟡 | CI `.github/ci/smoke_test.sh` (✅ after its first green run) |
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

---

## Details

### BUG-001

**`web` service runs the API image.** `docker-compose.yml` used `corp-library-api:latest` for `web`. That
image runs uvicorn on 8000; Traefik routes to port 80, so every request would get a 502.

- **Fix:** `image: ghcr.io/jlleongarcia/corp-library-web:latest`.
- **Files:** `docker-compose.yml`
- **Status:** 🟡 Fixed in code. Confirm with the first deployment (images aren't published yet).

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
- **Status:** 🟡 Fixed in code; no Docker on the dev PC to run nginx. Confirm with `curl -I` on the server.

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

---

## Adding a bug

1. Next free ID; add a row to the summary table (status ⬜).
2. Add a `### BUG-NNN` section: what goes wrong and when, the fix, files touched.
3. When fixed, add a regression test where possible, put its name in *Check*, and switch to ✅
   (or 🟡 if only the real environment can confirm it).
