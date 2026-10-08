from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import model_keyword_links
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.model import Model


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)

    models: Mapped[list["Model"]] = relationship(
        secondary=model_keyword_links, back_populates="keywords"
    )
