from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.disposition import Disposition

# When a secondary mission can be completed: during its owner's turn, during
# their opponent's, or either (e.g. "at the end of a turn").
SECONDARY_COMPLETES_ON = ("your_turn", "opponent_turn", "either")


class SecondaryMission(Base):
    __tablename__ = "secondary_missions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    completes_on: Mapped[str] = mapped_column(String(32))
    # VP for completing it in each mode; None means it can't be used in that
    # mode (e.g. a tactical-only card).
    fixed_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tactical_points: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PrimaryMission(Base):
    # The primary mission a player gets, given their disposition and their
    # opponent's.
    __tablename__ = "primary_missions"
    __table_args__ = (UniqueConstraint("player_disposition_id", "opponent_disposition_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    player_disposition_id: Mapped[int] = mapped_column(ForeignKey("dispositions.id"))
    opponent_disposition_id: Mapped[int] = mapped_column(ForeignKey("dispositions.id"))

    player_disposition: Mapped["Disposition"] = relationship(
        foreign_keys=[player_disposition_id]
    )
    opponent_disposition: Mapped["Disposition"] = relationship(
        foreign_keys=[opponent_disposition_id]
    )
