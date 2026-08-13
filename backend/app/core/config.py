from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-var-driven configuration (SEC-4). No secrets are hardcoded."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    oltp_schema: str = "atlas_oltp"
    olap_schema: str = "atlas_olap"

    database_url_oltp: str = ""
    database_url_olap: str = ""

    # Dashboard API (Phase 6): read-only against atlas_olap via the
    # atlas_reporting role (SEC-3) — deliberately never database_url_olap
    # (that connection string is the ETL's read/write role). Falls back to
    # database_url_olap only if unset, so local dev without the role
    # provisioned yet doesn't hard-fail — but the dashboard API should
    # always be pointed at atlas_reporting in any real deployment.
    database_url_olap_reporting: str = ""

    # Decision Support module (Phase 7): the only connection the
    # forecasting/optimization code uses — read on all of atlas_olap,
    # write only on its own ds_* tables (docs/phase7-architecture.md §6).
    # Never database_url_olap (the ETL's role) or database_url_olap_reporting
    # (atlas_reporting is contractually read-only everywhere, including
    # to ds_* tables — it must never gain write access to anything).
    database_url_olap_decision_support: str = ""

    # CORS: the dashboard frontend's own origin, nothing else (SEC-5 — a
    # role header is only meaningful coming from a trusted frontend).
    frontend_origin: str = "http://localhost:3000"

    @property
    def dashboard_db_url(self) -> str:
        return self.database_url_olap_reporting or self.database_url_olap

    @property
    def decision_support_db_url(self) -> str:
        return self.database_url_olap_decision_support or self.database_url_olap


settings = Settings()
