from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.faction import Faction
    from app.models.unit import Unit


class FactionUnit(Base):
    __tablename__ = "faction_units"
    __table_args__ = (UniqueConstraint("faction_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))

    faction: Mapped["Faction"] = relationship(back_populates="faction_units")
    units: Mapped[list["Unit"]] = relationship(back_populates="faction_unit")
    # The datasheets it can lead, if it's a leader or support datasheet.
    bodyguard_links: Mapped[list["LeaderBodyguard"]] = relationship(
        foreign_keys="LeaderBodyguard.leader_id", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def bodyguard_ids(self) -> list[int]:
        return sorted(link.bodyguard_id for link in self.bodyguard_links)


class LeaderBodyguard(Base):
    # A bodyguard datasheet a leader or support datasheet can lead (Core Rules
    # 19.01: "Leader and support units can only lead specific bodyguard
    # units").
    __tablename__ = "leader_bodyguards"

    leader_id: Mapped[int] = mapped_column(
        ForeignKey("faction_units.id", ondelete="CASCADE"), primary_key=True
    )
    bodyguard_id: Mapped[int] = mapped_column(
        ForeignKey("faction_units.id", ondelete="CASCADE"), primary_key=True
    )


class DatasheetLoadout(Base):
    # What a datasheet's units can be made of, from its datasheets.json entry
    # (seeded - replaced from the data at each start; see app/data/README.md):
    # - models: its models' names;
    # - composition: [{"model", "min", "max", "equipped": [item names]}] -
    #   empty when the data doesn't say (any number of its models, any of
    #   their weapons);
    # - options: its wargear options, [{"model", "with": [[item names]],
    #   "replace", "requires", "max", "per"}] (app.seeds.datasheets.OptionSpec).
    # Item names are weapon (by name without its profile) or wargear names.
    # See app/services/list_building/loadouts.py.
    __tablename__ = "datasheet_loadouts"

    faction_unit_id: Mapped[int] = mapped_column(
        ForeignKey("faction_units.id", ondelete="CASCADE"), primary_key=True
    )
    models: Mapped[list] = mapped_column(JSON, default=list)
    composition: Mapped[list] = mapped_column(JSON, default=list)
    options: Mapped[list] = mapped_column(JSON, default=list)
