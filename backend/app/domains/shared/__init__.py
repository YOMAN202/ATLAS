"""Cross-cutting components shared by every Domain Services module.

Kept deliberately small: only the typed exception hierarchy lives here.
Anything else that looks reusable belongs in the module that owns the
entity it touches (Master Prompt §15: a business rule lives in exactly
one place, but that place is the owning domain, not a generic bucket).
"""

from app.domains.shared.exceptions import (
    DomainError,
    EntityNotFoundError,
    InsufficientInventoryError,
    InvalidStateTransitionError,
    ReceiptToleranceExceededError,
    ZoneCapacityExceededError,
)
from app.domains.shared.lookups import get_code_by_id, get_id_by_code

__all__ = [
    "DomainError",
    "EntityNotFoundError",
    "InsufficientInventoryError",
    "InvalidStateTransitionError",
    "ReceiptToleranceExceededError",
    "ZoneCapacityExceededError",
    "get_code_by_id",
    "get_id_by_code",
]
