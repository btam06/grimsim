from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import enhancement_excluded_keywords, enhancement_keywords
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.datasheet_ability import DatasheetAbility
    from app.models.detachment import Detachment
    from app.models.keyword import Keyword
    from app.models.weapon_ability import WeaponAbility

# - "enhancement": carried by one CHARACTER model (not an EPIC HERO).
# - "upgrade": taken by a whole unit.
ENHANCEMENT_KINDS = ("enhancement", "upgrade")

# Who an ability an enhancement or upgrade grants applies to:
# - "bearer": the model carrying the enhancement (e.g. "ranged weapons
#   equipped by the bearer have [ANTI-INFANTRY 2+]");
# - "led_unit": every model in the bearer's unit, while it's leading one (e.g.
#   "while the bearer is leading a unit, models in that unit have Stealth");
# - "unit": every model in the unit - for upgrades.
ENHANCEMENT_SCOPES = ("bearer", "led_unit", "unit")
# The scopes each kind can use.
KIND_SCOPES = {"enhancement": ("bearer", "led_unit"), "upgrade": ("unit",)}


class Enhancement(Base):
    # An enhancement or upgrade from a detachment - only an army list that has
    # taken that detachment can use it, and each one at most once per list.
    __tablename__ = "enhancements"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    points: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    detachment_id: Mapped[int] = mapped_column(ForeignKey("detachments.id"))

    detachment: Mapped["Detachment"] = relationship()
    keywords: Mapped[list["Keyword"]] = relationship(
        secondary=enhancement_keywords, lazy="selectin"
    )
    excluded_keywords: Mapped[list["Keyword"]] = relationship(
        secondary=enhancement_excluded_keywords, lazy="selectin"
    )
    # Abilities it grants in combat.
    weapon_ability_grants: Mapped[list["EnhancementWeaponAbility"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    datasheet_ability_grants: Mapped[list["EnhancementDatasheetAbility"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class EnhancementWeaponAbility(Base):
    # A weapon ability an enhancement or upgrade gives weapons - all of them,
    # or only ranged or only melee ones (e.g. Peerless Eradicator: ranged
    # weapons in the led unit have [SUSTAINED HITS 1]).
    __tablename__ = "enhancement_weapon_abilities"

    enhancement_id: Mapped[int] = mapped_column(ForeignKey("enhancements.id"), primary_key=True)
    weapon_ability_id: Mapped[int] = mapped_column(
        ForeignKey("weapon_abilities.id"), primary_key=True
    )
    # "ranged", "melee", or None for every weapon.
    weapon_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope: Mapped[str] = mapped_column(String(32))

    weapon_ability: Mapped["WeaponAbility"] = relationship(lazy="selectin")


class EnhancementDatasheetAbility(Base):
    # A datasheet ability an enhancement or upgrade gives models (e.g.
    # Malphonic Susurrus: models in the led unit have Stealth).
    __tablename__ = "enhancement_datasheet_abilities"

    enhancement_id: Mapped[int] = mapped_column(ForeignKey("enhancements.id"), primary_key=True)
    datasheet_ability_id: Mapped[int] = mapped_column(
        ForeignKey("datasheet_abilities.id"), primary_key=True
    )
    scope: Mapped[str] = mapped_column(String(32))

    datasheet_ability: Mapped["DatasheetAbility"] = relationship(lazy="selectin")
