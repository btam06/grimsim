from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import (
    stratagem_conditions,
    stratagem_detachments,
    stratagem_effects,
)
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.condition import Condition
    from app.models.detachment import Detachment
    from app.models.effect import Effect


class Stratagem(Base):
    # A core stratagem (e.g. "Command Re-roll") is usable by any army and is
    # attached to no detachment; every other stratagem belongs to one or more
    # detachments and is only usable by an army that has taken one of them.
    __tablename__ = "stratagems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    cp: Mapped[int] = mapped_column(Integer)
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)

    # Same Condition/Effect catalog as the abilities - when a stratagem is used
    # in combat, its effects apply to the attacking unit like wargear abilities.
    conditions: Mapped[list["Condition"]] = relationship(secondary=stratagem_conditions)
    effects: Mapped[list["Effect"]] = relationship(secondary=stratagem_effects)

    detachments: Mapped[list["Detachment"]] = relationship(
        secondary=stratagem_detachments, back_populates="stratagems"
    )
