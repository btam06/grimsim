from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import datasheet_ability_links
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.model import Model


class DatasheetAbility(Base):
    __tablename__ = "datasheet_abilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    models: Mapped[list["Model"]] = relationship(
        secondary=datasheet_ability_links, back_populates="abilities"
    )
