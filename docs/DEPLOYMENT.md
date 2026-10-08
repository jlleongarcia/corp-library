# Corp Library — Deployment

How to deploy, run and recover Corp Library on the department Linux server.

## Prerequisites

- Docker Engine with the Compose plugin
- The shared **traefik-proxy** project running on the server (it owns ports 80/443, terminates
  HTTPS and creates the `proxy` network this app joins). See its README.
- A DNS **A record** for the app's hostname (`APP_HOST`) pointing to the server
- From IT (see the IT requirements doc): the read-only scanner account, LDAP access, and firewall
  rules from the server to the file server (TCP 445) and domain controllers (TCP 636/389, 88)
- For single sign-on (optional at first; the sign-in form works without it): the SPN and keytab, the
  intranet-zone GPO and the proxy bypass. See [Single sign-on](#single-sign-on-kerberos) below

## How images get to the server

The server doesn't build anything. On every push to `main`, the GitHub workflow
(`.github/workflows/ci.yml`) runs the tests, builds the images and publishes them to GitHub Container
Registry.

> **Not enabled yet.** Image publishing stays off until the app is ready to deploy; until then the
> workflow only runs the tests. To enable it: repository **Settings → Secrets and variables → Actions →
> Variables → New repository variable** `PUBLISH_IMAGES` = `true`. After the first published run, set
> each package's visibility to **Public** (profile → Packages → package settings) so the server can
> pull without logging in.


| Image | Used by |
| --- | --- |
| `ghcr.io/jlleongarcia/corp-library-api` | `api` and `worker` |
| `ghcr.io/jlleongarcia/corp-library-web` | `web` |

Each build is tagged `latest` and `sha-<commit>` (e.g. `sha-3f2a9c1`). The server only needs the repo for
`docker-compose.yml`, `deploy/backup.sh` and its own `.env`, and must be able to reach `ghcr.io`
(through the corporate proxy if Docker uses one). The repository is public, so pulling needs no login;
if it ever becomes private, run once on the server
`docker login ghcr.io -u jlleongarcia` with a classic personal access token that has only `read:packages`.

## First deployment

```bash
git clone https://github.com/jlleongarcia/corp-library.git && cd corp-library
cp .env.example .env
nano .env        # set APP_HOST, POSTGRES_PASSWORD, ADMIN_USERS, LDAP_*, SMB_*, PRIVACY_*, LOGIN_*
mkdir -p certs && cp /path/to/internal-ca.pem certs/   # CA that signed the DCs' LDAPS certificates
mkdir -p secrets  # the Kerberos keytab goes here once IT provides it (see below)
docker compose pull
docker compose up -d
docker compose ps            # all services "running", api "healthy"
```

Then open `https://<APP_HOST>/`, sign in with your Windows account (you must be in `ADMIN_USERS`), and:

1. **Shares → Add share**: one per department share, e.g. `\\fileserver\Finance`.
2. **Shares → Scan all**. Follow progress in **Scan activity**. The first scan of ~2 TB walks every
   folder over SMB; expect anywhere from tens of minutes to a few hours depending on file count.
3. After the scans, the worker automatically resolves users/groups, **indexes the documents for search**
   and looks for duplicates. Indexing first makes every file findable by name and folder (minutes), then
   reads the text of Office, PDF and text files, with OCR for scanned PDFs. On 2 TB that second part
   takes many hours. It works in 20-minute rounds (`EXTRACT_JOB_MINUTES`), so the nightly scan is never
   held up, and search improves as it goes. Progress: **Scan activity → Search index**.

From then on everything runs nightly at `SCAN_HOUR` (default 02:00).

### Before people use it

- **Privacy notice.** Fill in `PRIVACY_CONTROLLER`, `PRIVACY_CONTROLLER_ID`, `PRIVACY_CONTROLLER_ADDRESS`
  and `PRIVACY_CONTACT` (and `PRIVACY_DPO` if there is one) with whoever handles data protection. Until
  then the notice at the bottom of every page shows `[pendiente: …]` and the api logs a warning at
  startup. The text itself is in `frontend/src/pages/PrivacyPage.tsx`; it describes what the app
  actually logs and for how long (`AUDIT_RETENTION_DAYS`, `SESSION_DAYS`, `BACKUP_KEEP_DAYS`), so
  review it with them as well.
- **Sign-in throttling.** Ask IT for the domain's account lockout policy and set `LOGIN_MAX_FAILURES`
  below its threshold and `LOGIN_WINDOW_MINUTES` at or above its reset time.
- **HTTPS only.** nginx sends `Strict-Transport-Security` (1 year): once a browser has visited over HTTPS
  it won't accept plain HTTP or click through a certificate warning for `APP_HOST`. Install the internal
  CA certificate in traefik-proxy first.

### Single sign-on (Kerberos)

Without it, people sign in with the form (Windows username and password) and stay signed in for
`SESSION_DAYS`. With it, domain PCs sign in without typing anything. What IT does:

1. **SPN** on a service account (the scanner account works):
   `setspn -S HTTP/<APP_HOST> svc-corplib-scan`. `APP_HOST` must be a DNS **A** record, not a CNAME:
   browsers ask for a ticket for the name the CNAME points to.
2. **Keytab** for that SPN (AES256), e.g.
   `ktpass /princ HTTP/<APP_HOST>@COMPANY.COM /mapuser svc-corplib-scan /crypto AES256-SHA1 /ptype KRB5_NT_PRINCIPAL /pass * /out http.keytab`.
   Careful: `ktpass` with `/pass` resets that account's password. Agree with IT whether to use a
   dedicated account instead.
3. **GPO**: `https://<APP_HOST>` in the Local Intranet zone, or Chrome/Edge's `AuthServerAllowlist`
   policy, so browsers send tickets to it.
4. **Proxy bypass** for `<APP_HOST>` on the PCs, if they use the corporate web proxy.

Then on the server:

```bash
cp http.keytab secrets/http.keytab
sudo chown 10001 secrets/http.keytab && chmod 400 secrets/http.keytab   # the containers run as uid 10001
# .env: KERBEROS_KEYTAB=/secrets/http.keytab   (KERBEROS_REALM only if it isn't LDAP_DOMAIN in capitals)
docker compose up -d
```

Test from a domain PC: open `https://<APP_HOST>/`. It should go straight to search; if it shows the
sign-in form, see the troubleshooting table. SSO users' groups are read with the `LDAP_BIND_DN`
account, which must be able to read `tokenGroups` (members of *Windows Authorization Access Group* can).

### Running without the proxy (testing)

To try the stack on a machine without traefik-proxy, publish the web container directly with a
`docker-compose.override.yml` (ignored by git):

```yaml
services:
  web:
    ports: ["8510:80"]
networks:
  proxy:
    external: false  # create a local network instead of joining traefik-proxy's
```

and set any value for `APP_HOST`. The app is then on `http://<machine>:8510`.

## Updating

Once the workflow for your commit is green on GitHub (Actions tab):

```bash
git pull                   # only needed if docker-compose.yml, deploy/ or .env.example changed
docker compose pull        # fetch the new :latest images
docker compose up -d       # recreates changed containers; the api applies migrations on start
docker image prune -f      # optional: remove old image layers
```

### Rolling back

Pin the previous build's tag (find it under the repo's **Packages**, or in the Actions run) for the three
app services in `docker-compose.yml`, e.g. `ghcr.io/jlleongarcia/corp-library-api:sha-3f2a9c1`, then
`docker compose up -d`. Switch back to `:latest` once the fix is published. Database migrations only
move forward, so roll back code across a migration only after checking it's compatible.

## Logs and status

```bash
docker compose logs -f worker   # scans, LDAP lookups, indexing, dedupe
docker compose logs -f api      # sign-ins, SSO and permission-check failures
```

Who searched, viewed or downloaded what is in **Admin → Audit log** (CSV export), kept for
`AUDIT_RETENTION_DAYS`.

Scan errors (unreadable folders, permission problems) are also listed per run in **Scan activity**.
A run with some errors is marked `partial`: folders that couldn't be read keep their previous data.

## Backups

The `backup` service writes `corplib-YYYYMMDD-HHMM.dump` to `BACKUP_DIR` (default `./backups`)
every night at `BACKUP_HOUR` and keeps `BACKUP_KEEP_DAYS` days. Copy that folder somewhere off the
server as part of your normal backup routine.

The database only holds the index and reports; it can always be rebuilt by rescanning. Backups save
the rescan time and the scan history.

### Restore

```bash
docker compose stop api worker
docker compose exec -T db dropdb -U corplib corplib
docker compose exec -T db createdb -U corplib corplib
docker compose exec -T db pg_restore -U corplib -d corplib < backups/corplib-YYYYMMDD-HHMM.dump
docker compose start api worker
```

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| api keeps restarting, log says `DEV_MODE must not be enabled…` or `DEV_MODE only works with a local database` | `DEV_MODE=true` in the server's `.env`: set it to `false` |
| Domain PCs get the sign-in form instead of SSO | Site not in the Local Intranet zone / allowlist, SPN missing or duplicated (`setspn -Q HTTP/<APP_HOST>`), hostname is a CNAME, or `KERBEROS_KEYTAB` unset. The api log says why a ticket was rejected |
| SSO or sign-in says "Active Directory can't be reached" | The `LDAP_BIND_DN` account can't log in or can't read `tokenGroups`, or the DCs are unreachable |
| Downloads fail with "can't be reached to check your access" | The api container can't reach the file server over SMB (opening a file re-checks its permissions live) |
| Scanned PDFs are found by name only | `OCR_ENABLED=false`, or they were indexed before OCR was available: **Scan activity → Index now (retry failed)** |
| Some documents are "Unreadable" with "crashed the text extractor", "took more than … s" or "worker stopped while reading" | That file broke or overloaded the PDF/Office reader; the rest were indexed. Usually a damaged file. Raise `EXTRACT_TIMEOUT_SECONDS` / `EXTRACT_MEMORY_MB` if many big scans fail this way, then **Index now (retry failed)** |
| Sign-in says "Too many failed sign-ins for this account" | `LOGIN_MAX_FAILURES` wrong passwords within `LOGIN_WINDOW_MINUTES`: wait, or restart the api to clear it (the person's AD account isn't locked by this) |
| Privacy notice shows `[pendiente: …]` | The `PRIVACY_*` settings in `.env` are empty |
| Every LDAP sign-in fails; log mentions certificate / `invalid CA public key file` | `certs/internal-ca.pem` missing, or `LDAP_SERVER` isn't the name on the DC's certificate (use the FQDN, not an IP) |
| Scan fails immediately with a logon error | `SMB_USERNAME`/`SMB_PASSWORD` wrong, or account locked/expired |
| Folders show "ACL unreadable" | The scanner account lacks *Read permissions* on that folder |
| Permission grid shows "unresolved" accounts | Local groups on the file server or deleted users; LDAP can't name them |
| Everyone shows "none" in the grid | Users/groups not resolved yet: run **Refresh users & groups**, check `LDAP_BIND_*` |
| Login fails for everyone | LDAP settings, or the server can't reach the domain controllers |
| `network proxy declared as external, but could not be found` | Start the traefik-proxy project first |
| Browser shows Traefik's "404 page not found" | `APP_HOST` doesn't match the URL used, or the `web` container isn't running |
| Browser warns about the certificate | traefik-proxy has no certificate configured yet (self-signed fallback) |
| Browser shows a proxy error page | The PC sends intranet traffic through the corporate proxy; IT must add the app's hostname to the proxy bypass list |
