from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.model import Model


class Wargear(Base):
    __tablename__ = "wargear"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))

    model: Mapped["Model"] = relationship(back_populates="wargear")
