#!/usr/bin/env bash
# CI smoke test of the production stack: docker-compose.yml with .env.example,
# run from the images built in this CI run (tagged as the ghcr.io names Compose
# expects), checked through nginx as Traefik would reach it.
#
# Covers what the test suite can't: migrations on a fresh database, api and
# worker staying up, nginx routing (/api prefix, download location) and its
# security headers on every kind of response (BUG-011).
set -euo pipefail
cd "$(dirname "$0")/../.."

# The example config, made runnable: a password, no nightly scan, no LDAPS CA
# file, and a domain controller that can't resolve (.invalid never does).
sed -e 's/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=ci-password/' \
    -e 's/^SCAN_HOUR=.*/SCAN_HOUR=-1/' \
    -e 's|^LDAP_CA_CERT_FILE=.*|LDAP_CA_CERT_FILE=|' \
    -e 's/^LDAP_SERVER=.*/LDAP_SERVER=dc01.corp.invalid/' \
    .env.example > .env

compose() { docker compose -f docker-compose.yml -f .github/ci/compose.ci.yml "$@"; }
docker network inspect proxy >/dev/null 2>&1 || docker network create proxy  # owned by Traefik in production
compose up -d --wait --wait-timeout 180  # api only turns healthy after `alembic upgrade head`

BASE=http://127.0.0.1:8080
failures=0
pass() { echo "ok    $*"; }
fail() { echo "FAIL  $*" >&2; failures=$((failures + 1)); }

status() { curl -s -o /dev/null -w '%{http_code}' -m 30 "$@"; }
headers() { curl -s -o /dev/null -D - -m 30 "$1" | tr -d '\r'; }

expect_status() {  # expected url [curl args...]
  local want=$1 url=$2 got
  shift 2
  got=$(status "$@" "$url")
  [[ $got == "$want" ]] && pass "$url -> $got" || fail "$url -> $got (expected $want)"
}

expect_headers() {  # url header...
  local url=$1 h want
  shift
  h=$(headers "$url")
  for want in "$@"; do
    grep -qix "$want" <<<"$h" && pass "$url has '$want'" || fail "$url lacks '$want'"$'\n'"$h"
  done
}

SECURITY=("X-Content-Type-Options: nosniff" "X-Frame-Options: SAMEORIGIN" "Referrer-Policy: same-origin"
          "Strict-Transport-Security: max-age=31536000")

# API reachable through nginx, with the /api prefix stripped.
expect_status 200 "$BASE/api/health"
curl -fsS "$BASE/api/auth/config" | grep -q '"sso_enabled":false' \
  && pass "/api/auth/config: SSO off without a keytab" || fail "/api/auth/config"
# Signed out: the API answers 401, through the general and the download locations.
expect_status 401 "$BASE/api/auth/me"
expect_status 401 "$BASE/api/documents/1/download"
# Active Directory unreachable: the sign-in form says so instead of failing.
expect_status 503 "$BASE/api/auth/login" -X POST -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" -d '{"username":"someone","password":"x"}'

# Security headers on every location, success or error (BUG-011).
asset=$(curl -fsS "$BASE/" | grep -o '/assets/[^"]*\.js' | head -n1)
[[ -n $asset ]] && pass "index.html references $asset" || fail "no /assets/*.js in index.html"
expect_headers "$BASE/" "${SECURITY[@]}" "Cache-Control: no-cache"
expect_headers "$BASE/search" "${SECURITY[@]}" "Cache-Control: no-cache"  # SPA fallback
expect_headers "$BASE$asset" "${SECURITY[@]}" "Cache-Control: public, immutable"
expect_headers "$BASE/api/health" "${SECURITY[@]}"
expect_headers "$BASE/api/documents/1/download" "${SECURITY[@]}"

# CSP on the UI only (BUG-031): a PDF preview served with it wouldn't render.
headers "$BASE/" | grep -qi "^Content-Security-Policy: default-src 'self'; script-src 'self';" \
  && pass "UI has the Content-Security-Policy" || fail "UI lacks the Content-Security-Policy"
headers "$BASE/api/documents/1/preview" | grep -qi "^Content-Security-Policy:" \
  && fail "API responses must not carry the UI's CSP" || pass "API responses have no CSP"
# Nothing loaded from other sites (BUG-034).
curl -fsS "$BASE/" | grep -qiE "https?://" \
  && fail "index.html references another site" || pass "index.html loads nothing from other sites"
# A download link opened by the browser gets a page, not JSON (BUG-028).
curl -s -m 30 -H "Sec-Fetch-Dest: document" "$BASE/api/documents/1/download" | grep -q 'href="/login"' \
  && pass "download link without a session: sign-in page" || fail "download link without a session"

# Nothing crashed and restarted behind --wait's back (the worker has no healthcheck).
sleep 10
for svc in api worker web; do
  id=$(compose ps -q "$svc")
  state=$(docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' "$id")
  [[ $state == "running restarts=0" ]] && pass "$svc $state" || fail "$svc $state"
done

if ((failures)); then
  echo "$failures check(s) failed" >&2
  exit 1
fi
echo "smoke test passed"
