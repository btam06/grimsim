from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import wargear_ability_links
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.model import Model
    from app.models.wargear_ability import WargearAbility


class Wargear(Base):
    __tablename__ = "wargear"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))

    model: Mapped["Model"] = relationship(back_populates="wargear")
    abilities: Mapped[list["WargearAbility"]] = relationship(
        secondary=wargear_ability_links, back_populates="wargear"
    )
    scope_link: Mapped["WargearScope | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def scope(self) -> str:
        # Who its abilities reach (see WARGEAR_SCOPES).
        return self.scope_link.scope if self.scope_link else "bearer"

    @scope.setter
    def scope(self, scope: str) -> None:
        self.scope_link = WargearScope(scope=scope) if scope != "bearer" else None


# Who a piece of wargear's abilities reach:
# - "bearer": the weapons of the model equipped with it;
# - "bearers_unit": the weapons of every model in the bearer's unit (e.g.
#   Omnispex: "ranged weapons equipped by models in the bearer's unit have
#   [IGNORES COVER]").
WARGEAR_SCOPES = ("bearer", "bearers_unit")


class WargearScope(Base):
    # A piece of wargear's scope, when it isn't "bearer". Its own table rather
    # than a column on wargear, so existing databases pick it up without a
    # migration.
    __tablename__ = "wargear_scopes"

    wargear_id: Mapped[int] = mapped_column(ForeignKey("wargear.id"), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32))
