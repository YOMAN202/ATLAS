"""Generic helpers for the constrained-enumeration lookup tables (Master
Prompt §5 / TDD §4.1: "status fields as constrained lookup tables, never
free text"). Every lookup model shares the same shape (surrogate id plus
a unique `code`), so resolving one by its business code — or vice versa
— is identical logic across POStatus, OrderStatus, ShipmentStatus, and
the rest. Implemented once here rather than once per domain module.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.shared.exceptions import EntityNotFoundError


def get_id_by_code(session: Session, model: type, code: str) -> int:
    """Resolve a lookup table's surrogate id from its business `code`."""

    row_id = session.execute(select(model.id).where(model.code == code)).scalar_one_or_none()
    if row_id is None:
        raise EntityNotFoundError(f"{model.__name__} '{code}' does not exist")
    return row_id


def get_code_by_id(session: Session, model: type, row_id: int) -> str:
    """Resolve a lookup table's business `code` from its surrogate id."""

    row = session.get(model, row_id)
    if row is None:
        raise EntityNotFoundError(f"{model.__name__} {row_id} does not exist")
    return row.code
