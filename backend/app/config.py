from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode

# Local development reads the repo-root .env (the same file docker compose uses).
# In containers the variables come from the environment and this file doesn't exist.
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


def _split_csv(value):
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


class Settings(BaseSettings):
    app_name: str = "Corp Library"
    secret_key: str = "change-this-in-production-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    database_url: str = "postgresql+psycopg://corplib:corplib@db:5432/corplib"

    # Admins of the app (sAMAccountName, case-insensitive). Comma-separated in .env.
    admin_users: Annotated[list[str], NoDecode] = []

    # ── LDAP / Active Directory ───────────────────────────────────────────────
    ldap_server: str = ""
    ldap_port: int = 636
    ldap_use_ssl: bool = True
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

    # ── Duplicate detection ───────────────────────────────────────────────────
    dedupe_min_size: int = 1024  # bytes; tiny files aren't worth reporting
    dedupe_full_hash_max_size: int = 512 * 1024 * 1024  # above this, quick hash only

    # ── Permissions ───────────────────────────────────────────────────────────
    # Extra SIDs every domain user has on the file server, beyond Everyone /
    # Authenticated Users / Network. BUILTIN\Users contains Domain Users by default.
    extra_baseline_sids: Annotated[list[str], NoDecode] = ["S-1-5-32-545"]

    # ── Dev mode ──────────────────────────────────────────────────────────────
    # Skips LDAP: any username with DEV_PASSWORD logs in. Refused if LDAP is configured.
    dev_mode: bool = False
    dev_password: str = "dev"

    model_config = {"env_file": ROOT_ENV, "env_file_encoding": "utf-8", "case_sensitive": False, "extra": "ignore"}

    _split = field_validator(
        "admin_users", "scan_ignore_names", "scan_ignore_prefixes", "extra_baseline_sids",
        mode="before",
    )(_split_csv)


settings = Settings()
