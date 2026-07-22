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


settings = Settings()
