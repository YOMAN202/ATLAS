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

    # Phase 8 copilot (docs/phase8-analytics-copilot.md): the base URL the
    # copilot's tool layer calls, over the SAME read-only dashboard API
    # every frontend request already uses -- no new DB credential, no new
    # trust boundary (see ADR-023, docs/ATLAS-TDD.md §14). Unset by
    # default (empty), same as never having configured it; the copilot
    # tool layer fails loudly, not silently, if a tool is invoked without
    # one.
    copilot_api_base_url: str = ""

    # Real claim-drafting LLM credential (ADR-023) -- kept as an optional
    # future provider per Phase 8.1's provider-abstraction decision
    # (ADR-024, docs/ATLAS-TDD.md §14). Not wired to any live endpoint;
    # AnthropicClaimDraftingClient still raises NotImplementedError.
    # Never required for the CI-blocking verification harness, which
    # runs entirely against FixtureClaimDraftingClient.
    anthropic_api_key: str = ""

    # Phase 8.1: which LLM provider powers the live chat interface
    # (app/copilot/provider.py's configuration-driven dispatch). Gemini
    # (Google AI Studio) is the primary/default provider; "anthropic" is
    # accepted by the dispatcher but has no live agentic implementation
    # yet (ADR-024).
    copilot_llm_provider: str = "gemini"

    # Google AI Studio credential for the live copilot chat interface
    # (Phase 8.1, ADR-024). Read from GEMINI_API_KEY.
    # GeminiClaimDraftingClient / run_agentic_pipeline raise a clear
    # configuration error rather than silently falling back to anything
    # if this is unset. Never required for the CI-blocking verification
    # harness, which runs entirely against FixtureClaimDraftingClient.
    gemini_api_key: str = ""

    # Model ID for the live Gemini agentic loop -- kept as a setting
    # (not a hardcoded constant) so it can be corrected without a code
    # change if live validation shows the default is wrong for this
    # account/API version.
    copilot_gemini_model: str = "gemini-3.7-flash"

    @property
    def dashboard_db_url(self) -> str:
        return self.database_url_olap_reporting or self.database_url_olap

    @property
    def decision_support_db_url(self) -> str:
        return self.database_url_olap_decision_support or self.database_url_olap


settings = Settings()
