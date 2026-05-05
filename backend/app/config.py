from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Corp Library"
    secret_key: str = "change-this-in-production-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8-hour work day

    database_url: str = "sqlite:////app/data/corp_library.db"

    # LDAP / Active Directory
    ldap_server: str = "ldap.company.com"
    ldap_port: int = 389
    ldap_use_ssl: bool = False
    ldap_domain: str = "company.com"
    ldap_base_dn: str = "DC=company,DC=com"
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_user_search_base: str = ""
    ldap_user_filter: str = "(sAMAccountName={username})"
    ldap_group_attribute: str = "memberOf"

    # Dev mode — bypasses LDAP with a local admin account
    dev_mode: bool = True
    dev_admin_username: str = "admin"
    dev_admin_password: str = "admin123"

    # Scanner
    scan_interval_hours: int = 6

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
