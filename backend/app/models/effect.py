from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Effect(Base):
    # A hardcoded, seeded catalog of effects a WeaponAbility can apply during
    # combat resolution. `keyword` matches an entry in
    # app/combat_rules/effects.py, which is what the engine actually runs.
    __tablename__ = "effects"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
