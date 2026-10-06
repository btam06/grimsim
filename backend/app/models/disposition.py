from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import detachment_dispositions
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.detachment import Detachment


class Disposition(Base):
    __tablename__ = "dispositions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    detachments: Mapped[list["Detachment"]] = relationship(
        secondary=detachment_dispositions, back_populates="dispositions"
    )
