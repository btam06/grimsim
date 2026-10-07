from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Condition(Base):
    # A hardcoded, seeded catalog of conditions a WeaponAbility can check for
    # during combat resolution. `keyword` matches an entry in
    # app/combat_rules/conditions.py, which is what the engine actually runs.
    __tablename__ = "conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
