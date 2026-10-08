from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode
from sqlalchemy.engine import make_url

# Local development reads the repo-root .env (the same file docker compose uses).
# In containers the variables come from the environment and this file doesn't exist.
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


def _split_csv(value):
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


class Settings(BaseSettings):
    app_name: str = "Corp Library"

    database_url: str = "postgresql+psycopg://corplib:corplib@db:5432/corplib"

    # Admins of the app (sAMAccountName, case-insensitive). Comma-separated in .env.
    admin_users: Annotated[list[str], NoDecode] = []

    # ── Sessions ──────────────────────────────────────────────────────────────
    # Sliding expiry: using the app pushes it forward.
    session_days: int = 30
    # Group memberships are read at sign-in and re-read from AD this often, so
    # removing someone from a group takes effect within this time.
    groups_refresh_hours: int = 8
    # The session cookie is only sent over HTTPS. Turn off only for local development.
    cookie_secure: bool = True

    # ── Kerberos SSO ──────────────────────────────────────────────────────────
    # Keytab for HTTP/<APP_HOST>, from IT. Empty = SSO off; the sign-in form still works.
    kerberos_keytab: str = ""
    # Realm accepted in tickets; empty = LDAP_DOMAIN in upper case.
    kerberos_realm: str = ""

    # ── LDAP / Active Directory ───────────────────────────────────────────────
    ldap_server: str = ""
    ldap_port: int = 636
    ldap_use_ssl: bool = True
    # PEM file with the internal CA that signed the domain controllers' certificates.
    # Empty = the system CA store. The certificate is always validated.
    ldap_ca_cert_file: str = ""
    ldap_domain: str = "company.com"
    ldap_base_dn: str = "DC=company,DC=com"
    ldap_bind_dn: str = ""  # service account used for directory lookups
    ldap_bind_password: str = ""
    ldap_user_search_base: str = ""
    ldap_user_filter: str = "(sAMAccountName={username})"

    # ── SMB (file server) ─────────────────────────────────────────────────────
    smb_username: str = ""  # e.g. DOMAIN\svc-corplib-scan or svc-corplib-scan@domain
    smb_password: str = ""
    smb_auth_protocol: str = "negotiate"  # negotiate | kerberos | ntlm

    # ── Scanner ───────────────────────────────────────────────────────────────
    scan_hour: int = 2  # local hour of the nightly scan; -1 disables the schedule
    scan_ignore_names: Annotated[list[str], NoDecode] = [
        "Thumbs.db", "desktop.ini", ".DS_Store", "$RECYCLE.BIN",
        "System Volume Information", "DfsrPrivate", "~snapshot",
    ]
    scan_ignore_prefixes: Annotated[list[str], NoDecode] = ["~$"]  # Office lock files
    scan_commit_every: int = 200  # folders per transaction

    # ── Content extraction ────────────────────────────────────────────────────
    extract_max_size: int = 50 * 1024 * 1024  # bytes; bigger files are indexed by name only
    extract_max_chars: int = 200_000  # text kept per document, for search and snippets
    # Scanned PDFs are read with Tesseract (installed in the Docker image). Without
    # the binary, they're indexed by name only and flagged "ocr unavailable".
    ocr_enabled: bool = True
    ocr_languages: str = "spa+eng"
    ocr_max_pages: int = 30
    tesseract_cmd: str = "tesseract"
    # A long extraction job hands the worker back after this long, so scans aren't held up.
    extract_job_minutes: int = 20

    # ── Audit log ─────────────────────────────────────────────────────────────
    audit_retention_days: int = 365  # 0 keeps everything

    # ── Duplicate detection ───────────────────────────────────────────────────
    dedupe_min_size: int = 1024  # bytes; tiny files aren't worth reporting
    dedupe_full_hash_max_size: int = 512 * 1024 * 1024  # above this, quick hash only

    # ── Permissions ───────────────────────────────────────────────────────────
    # Extra SIDs every domain user has on the file server, beyond Everyone /
    # Authenticated Users / Network. BUILTIN\Users contains Domain Users by default.
    extra_baseline_sids: Annotated[list[str], NoDecode] = ["S-1-5-32-545"]

    # ── Dev mode ──────────────────────────────────────────────────────────────
    # Sign in as any username, without a password, with fake groups. Only possible on
    # a developer PC: see dev_mode_problem().
    dev_mode: bool = False
    # Fake group memberships, e.g. "alice:hr,finance;bob:finance". The groups are
    # matched by name in the .corplib-acl.json files of local test shares.
    dev_groups: str = ""

    model_config = {"env_file": ROOT_ENV, "env_file_encoding": "utf-8", "case_sensitive": False, "extra": "ignore"}

    _split = field_validator(
        "admin_users", "scan_ignore_names", "scan_ignore_prefixes", "extra_baseline_sids",
        mode="before",
    )(_split_csv)

    @property
    def sso_enabled(self) -> bool:
        return bool(self.kerberos_keytab)


LOCAL_DB_HOSTS = {None, "", "localhost", "127.0.0.1", "::1"}


def dev_mode_problem(s: Settings) -> str | None:
    """
    Why DEV_MODE can't run with these settings, or None if it can.

    Dev sign-in takes no password, so it must be impossible in production. The
    production stack always has Active Directory configured and its database in
    the `db` container; a developer PC has neither.
    """
    if s.ldap_server or s.kerberos_keytab:
        return "DEV_MODE must not be enabled when LDAP_SERVER or KERBEROS_KEYTAB is set"
    if make_url(s.database_url).host not in LOCAL_DB_HOSTS:
        return "DEV_MODE only works with a local database (scripts/dev.py or the tests)"
    return None


settings = Settings()
