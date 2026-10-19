from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import list_owners
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.army_list import ArmyList


class User(Base):
    # A player. Just a name - no account or login.
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)

    lists: Mapped[list["ArmyList"]] = relationship(secondary=list_owners, back_populates="owner")
