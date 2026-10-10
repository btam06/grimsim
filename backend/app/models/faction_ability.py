from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.faction import Faction


class FactionAbility(Base):
    # A faction-wide special rule (e.g. "Oath of Moment", "Waaagh!") - purely
    # descriptive, unlike WeaponAbility/WargearAbility/DatasheetAbility there
    # are deliberately no conditions/effects here for the combat engine to key
    # off; it exists for reference only.
    __tablename__ = "faction_abilities"
    __table_args__ = (UniqueConstraint("faction_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))

    faction: Mapped["Faction"] = relationship(back_populates="faction_abilities")
