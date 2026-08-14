"""Citation objects (docs/phase8-grounding-spec.md §3): built entirely
by code from fields the existing dashboard endpoints already return.
The LLM never authors a citation -- it may only reference the
citation_id of an object created here, from real, retrieved data.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    citation_id: str
    endpoint: str
    source_tables: tuple[str, ...]
    model_id: int | None = None
    model_name: str | None = None
    source_forecast_model_id: int | None = None
    source_supplier_model_id: int | None = None
    source_service_level_model_id: int | None = None
    source_inventory_policy_model_id: int | None = None
    etl_run_id: int | None = None
    generated_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "citation_id": self.citation_id,
            "endpoint": self.endpoint,
            "source_tables": list(self.source_tables),
            "model_id": self.model_id,
            "model_name": self.model_name,
            "source_forecast_model_id": self.source_forecast_model_id,
            "source_supplier_model_id": self.source_supplier_model_id,
            "source_service_level_model_id": self.source_service_level_model_id,
            "source_inventory_policy_model_id": self.source_inventory_policy_model_id,
            "etl_run_id": self.etl_run_id,
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True)
class ToolResult:
    """One tool call's outcome: the raw JSON payload the endpoint
    returned, plus the citation built from it. `payload` is what claim
    verification checks values against -- never re-derived, never
    summarized before verification."""

    tool_name: str
    payload: dict
    citation: Citation
