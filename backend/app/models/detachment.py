from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import detachment_dispositions, stratagem_detachments
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.disposition import Disposition
    from app.models.faction import Faction
    from app.models.stratagem import Stratagem


class Detachment(Base):
    __tablename__ = "detachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    faction_id: Mapped[int] = mapped_column(ForeignKey("factions.id"))
    dp: Mapped[int] = mapped_column(Integer)

    faction: Mapped["Faction"] = relationship(back_populates="detachments")
    dispositions: Mapped[list["Disposition"]] = relationship(
        secondary=detachment_dispositions, back_populates="detachments"
    )
    stratagems: Mapped[list["Stratagem"]] = relationship(
        secondary=stratagem_detachments, back_populates="detachments"
    )
    unique_tag_link: Mapped["DetachmentUniqueTag | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def unique_tag(self) -> str | None:
        # e.g. "DYNASTY": a list can't take two detachments with the same tag.
        return self.unique_tag_link.tag if self.unique_tag_link else None

    @unique_tag.setter
    def unique_tag(self, tag: str | None) -> None:
        self.unique_tag_link = DetachmentUniqueTag(tag=tag) if tag else None


class DetachmentUniqueTag(Base):
    # A detachment's unique tag (one at most). Its own table rather than a
    # column, so existing databases pick it up without a migration.
    __tablename__ = "detachment_unique_tags"

    detachment_id: Mapped[int] = mapped_column(ForeignKey("detachments.id"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(50))
