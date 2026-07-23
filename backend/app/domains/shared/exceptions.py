"""Shared business-rule exception hierarchy for the Domain Services layer.

Centralized here so every module raises from the same typed hierarchy
instead of each inventing its own ad-hoc exceptions (Master Prompt §15:
"a business rule lives in exactly one place"). This is also the single
place Phase 6's API layer will need to map exceptions to HTTP responses
(Master Prompt §6: "Define typed domain exceptions and map them to HTTP
responses centrally").
"""


class DomainError(Exception):
    """Base class for all Domain Service business-rule violations.

    `rule` is the SRS BR-/FR- identifier the violation traces back to,
    where one applies (Master Prompt §12: every business rule is
    traceable to its SRS id). Not every DomainError maps to a single
    numbered rule (e.g. a not-found lookup), so `rule` is optional.
    """

    def __init__(self, message: str, *, rule: str | None = None) -> None:
        super().__init__(message)
        self.rule = rule


class EntityNotFoundError(DomainError):
    """Raised when a service function is given an id/code that does not
    exist. Not a business-rule violation itself — a referential-integrity
    failure at the service boundary, kept typed so callers never have to
    catch a bare SQLAlchemy/KeyError instead."""


class InvalidStateTransitionError(DomainError):
    """Raised when an operation is attempted against an entity that is not
    in a state that permits it — e.g. submitting a PO that isn't in DRAFT,
    allocating an order line that is already fully resolved, an
    out-of-sequence shipment status change, re-inspecting an already
    inspected return line."""


class InsufficientInventoryError(DomainError):
    """BR-2: inventory cannot go negative. Raised before any write is
    attempted, so the caller gets a clear typed error instead of the
    database CHECK constraint's OperationalError surfacing from below."""


class ZoneCapacityExceededError(DomainError):
    """FR-2.2: a warehouse zone's modeled capacity would be exceeded by the
    requested movement."""


class ReceiptToleranceExceededError(DomainError):
    """BR-1: an explicit request to mark a purchase order fulfilled while
    one or more lines are not within the approved receipt tolerance."""
