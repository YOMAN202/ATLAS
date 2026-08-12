"""etl_watermark read/advance (ADR-008, ADR-017).

Advancement is intentionally NOT exposed as "set to X" from outside this
module — the only supported operation is advance_if_later(), which never
moves a watermark backward and is the sole point where the ADR-017 rule
("advance only past what is durably accounted for") is enforced.
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


def get_watermark(conn: Connection, source_table: str) -> datetime | None:
    """Returns the last_extracted_at for a table, or None if the table
    has never been successfully processed (extract everything)."""

    row = conn.execute(
        text("SELECT last_extracted_at FROM etl_watermark WHERE source_table = :t"),
        {"t": source_table},
    ).one_or_none()
    return row[0] if row else None


def advance_if_later(conn: Connection, source_table: str, new_watermark: datetime) -> None:
    """Advances source_table's watermark to new_watermark — but only if
    new_watermark is actually later than the current value (or no
    watermark row exists yet). Never moves backward; a no-op call (e.g.
    an empty batch) is safe.
    """

    current = get_watermark(conn, source_table)
    if current is not None and new_watermark <= current:
        return

    conn.execute(
        text(
            "INSERT INTO etl_watermark (source_table, last_extracted_at, updated_at) "
            "VALUES (:t, :w, NOW()) "
            "ON DUPLICATE KEY UPDATE last_extracted_at = :w, updated_at = NOW()"
        ),
        {"t": source_table, "w": new_watermark},
    )
