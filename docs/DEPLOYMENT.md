# Corp Library — Deployment

How to deploy, run and recover Corp Library on the department Linux server.

## Prerequisites

- Docker Engine with the Compose plugin
- The shared **traefik-proxy** project running on the server (it owns ports 80/443, terminates
  HTTPS and creates the `proxy` network this app joins). See its README.
- A DNS **A record** for the app's hostname (`APP_HOST`) pointing to the server
- From IT (see the IT requirements doc): the read-only scanner account, LDAP access, and firewall
  rules from the server to the file server (TCP 445) and domain controllers (TCP 636/389, 88)

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
nano .env        # set APP_HOST, SECRET_KEY, POSTGRES_PASSWORD, ADMIN_USERS, LDAP_*, SMB_*
docker compose pull
docker compose up -d
docker compose ps            # all services "running", api "healthy"
```

Then open `https://<APP_HOST>/`, sign in with your Windows account (you must be in `ADMIN_USERS`), and:

1. **Shares → Add share**: one per department share, e.g. `\\fileserver\Finance`.
2. **Shares → Scan all**. Follow progress in **Scan activity**. The first scan of ~2 TB walks every
   folder over SMB; expect anywhere from tens of minutes to a few hours depending on file count.
3. After the scans, the worker automatically resolves users/groups and looks for duplicates.
   Duplicate detection reads file contents (only for files whose size matches another file), so it
   takes longer than the scan.

From then on everything runs nightly at `SCAN_HOUR` (default 02:00).

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
docker compose logs -f worker   # scans, LDAP lookups, dedupe
docker compose logs -f api
```

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
| Scan fails immediately with a logon error | `SMB_USERNAME`/`SMB_PASSWORD` wrong, or account locked/expired |
| Folders show "ACL unreadable" | The scanner account lacks *Read permissions* on that folder |
| Permission grid shows "unresolved" accounts | Local groups on the file server or deleted users; LDAP can't name them |
| Everyone shows "none" in the grid | Users/groups not resolved yet: run **Refresh users & groups**, check `LDAP_BIND_*` |
| Login fails for everyone | LDAP settings, or the server can't reach the domain controllers |
| `network proxy declared as external, but could not be found` | Start the traefik-proxy project first |
| Browser shows Traefik's "404 page not found" | `APP_HOST` doesn't match the URL used, or the `web` container isn't running |
| Browser warns about the certificate | traefik-proxy has no certificate configured yet (self-signed fallback) |
| Browser shows a proxy error page | The PC sends intranet traffic through the corporate proxy; IT must add the app's hostname to the proxy bypass list |
