"""Claim data structures (docs/phase8-grounding-spec.md §1): the
structured intermediate representation the LLM drafts INTO, instead of
free prose. Every claim is typed and machine-checkable -- "is this
value really in the retrieved payload" is a lookup, not a judgment
call, which is the entire point of drafting claims before rendering
anything.
"""

from dataclasses import dataclass
from typing import Literal

Operation = Literal["difference", "sum", "pct_delta"]


@dataclass(frozen=True)
class FactClaim:
    """A single retrieved value, attributed to one citation.
    `metric_path` is a dotted path into that citation's tool payload,
    e.g. "summary.avg_risk_score" or "recommendation.safety_stock"."""

    metric_path: str
    value: float | int | str
    citation_id: str
    claim_type: Literal["fact"] = "fact"


@dataclass(frozen=True)
class ComparisonClaim:
    """A claim that one retrieved value is higher/lower/equal to
    another -- each value independently verified against its own
    citation, and the claimed direction checked against the actual
    values, not just each value in isolation."""

    metric_path: str
    value_a: float
    value_b: float
    direction: Literal["higher", "lower", "equal"]
    citation_id_a: str
    citation_id_b: str
    claim_type: Literal["comparison"] = "comparison"


@dataclass(frozen=True)
class DerivedClaim:
    """A claim computed from two retrieved operand values (a
    difference, sum, or percentage delta) -- legitimate arithmetic on
    real data, not fabrication, and verified by recomputing the same
    operation from the retrieved operands, not by literal lookup."""

    operation: Operation
    operand_metric_path_a: str
    operand_metric_path_b: str
    citation_id_a: str
    citation_id_b: str
    value: float
    claim_type: Literal["derived"] = "derived"


Claim = FactClaim | ComparisonClaim | DerivedClaim
