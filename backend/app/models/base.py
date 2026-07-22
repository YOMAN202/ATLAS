from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming convention so every constraint/index gets a deterministic,
# documented name (Master Prompt §5: "Index every foreign-key column and
# document it explicitly"; Roadmap Phase 1: "constraint tests pass").
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """created_at/updated_at on every OLTP table.

    Not requested by any single FR, but required structurally: TDD §6 /
    ADR-008 mandate watermark-based incremental ETL extraction, and
    Master Prompt §8 states watermark columns must be indexed. Retrofitting
    this after Phase 1 would be a destructive schema change, so it is added
    here, at initial schema design time, on every table.
    """

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False, index=True
    )
