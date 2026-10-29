from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, inspect
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import unit_upgrades
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.enhancement import Enhancement
    from app.models.army_list import ArmyList
    from app.models.faction_unit import FactionUnit
    from app.models.unit_model import UnitModel


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    faction_unit_id: Mapped[int] = mapped_column(ForeignKey("faction_units.id"))
    points: Mapped[int] = mapped_column(Integer)
    list_id: Mapped[int | None] = mapped_column(ForeignKey("lists.id"), nullable=True)

    faction_unit: Mapped["FactionUnit"] = relationship(back_populates="units")
    army_list: Mapped["ArmyList | None"] = relationship(back_populates="units")
    unit_models: Mapped[list["UnitModel"]] = relationship(
        back_populates="unit", cascade="all, delete-orphan"
    )
    # The unit's upgrade, if any.
    upgrade: Mapped["Enhancement | None"] = relationship(
        secondary=unit_upgrades, uselist=False, lazy="selectin"
    )
    # The detachment rules with a selection limit this unit was selected for.
    rule_selection_links: Mapped[list["UnitRuleSelection"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def label(self) -> str:
        # Its datasheet's name - numbered when its list has more than one unit
        # of it, in the list's order (e.g. "Skitarii Rangers 2"), to tell them
        # apart. Just the name if its list isn't loaded with it.
        name = self.faction_unit.name
        state = inspect(self)
        if "army_list" in state.unloaded or self.army_list is None:
            return name
        if "units" in inspect(self.army_list).unloaded:
            return name
        same = sorted(
            u.id for u in self.army_list.units if u.faction_unit_id == self.faction_unit_id
        )
        return f"{name} {same.index(self.id) + 1}" if len(same) > 1 and self.id in same else name

    @property
    def selected_rule_ids(self) -> list[int]:
        return [link.rule_id for link in self.rule_selection_links]

    @selected_rule_ids.setter
    def selected_rule_ids(self, rule_ids: list[int]) -> None:
        self.rule_selection_links = [UnitRuleSelection(rule_id=i) for i in rule_ids]


class UnitRuleSelection(Base):
    # A unit selected for a detachment rule with a selection limit (see
    # DetachmentRule.selection_limit).
    __tablename__ = "unit_rule_selections"

    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("detachment_rules.id"), primary_key=True)
