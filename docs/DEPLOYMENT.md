# Corp Library — Operations

How to deploy, run and recover Corp Library on the department Linux server.

## Prerequisites

- Docker Engine with the Compose plugin
- From IT (see the IT requirements doc): the read-only scanner account, LDAP access, and firewall
  rules from the server to the file server (TCP 445) and domain controllers (TCP 636/389, 88)

## First deployment

```bash
git clone <repo> corp-library && cd corp-library
cp .env.example .env
nano .env        # set SECRET_KEY, POSTGRES_PASSWORD, ADMIN_USERS, LDAP_*, SMB_*
docker compose up -d --build
docker compose ps            # all services "running", api "healthy"
```

Then open `http://<server>:8510/`, sign in with your Windows account (you must be in `ADMIN_USERS`), and:

1. **Shares → Add share**: one per department share, e.g. `\\fileserver\Finance`.
2. **Shares → Scan all**. Follow progress in **Scan activity**. The first scan of ~2 TB walks every
   folder over SMB; expect anywhere from tens of minutes to a few hours depending on file count.
3. After the scans, the worker automatically resolves users/groups and looks for duplicates.
   Duplicate detection reads file contents (only for files whose size matches another file), so it
   takes longer than the scan.

From then on everything runs nightly at `SCAN_HOUR` (default 02:00).

## Updating

```bash
git pull
docker compose up -d --build   # the api applies database migrations on start
```

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
| Browser shows a proxy error page | The PC sends intranet traffic through the corporate proxy; IT must add the app's hostname to the proxy bypass list |
