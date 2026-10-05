from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import unit_models
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.model import Model


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))

    models: Mapped[list["Model"]] = relationship(
        secondary=unit_models, back_populates="units"
    )
