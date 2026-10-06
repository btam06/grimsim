from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import weapon_ability_links
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.model import Model
    from app.models.weapon_ability import WeaponAbility


class Weapon(Base):
    __tablename__ = "weapons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    damage: Mapped[str] = mapped_column(String(10))
    range: Mapped[int] = mapped_column(Integer)
    strength: Mapped[int] = mapped_column(Integer)
    ap: Mapped[int] = mapped_column(Integer)
    attacks: Mapped[int] = mapped_column(Integer)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))

    model: Mapped["Model"] = relationship(back_populates="weapons")
    abilities: Mapped[list["WeaponAbility"]] = relationship(
        secondary=weapon_ability_links, back_populates="weapons"
    )
