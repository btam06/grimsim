from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.datasheet_ability import DatasheetAbility
    from app.models.keyword import Keyword
    from app.models.weapon_ability import WeaponAbility


class DetachmentRule(Base):
    # A detachment's rule. In combat it grants abilities to the units of a
    # list that has taken the detachment - those whose every model matches
    # one of its keyword options (e.g. Stealth Optimisation: SKITARII +
    # INFANTRY, SKITARII + MOUNTED and IRONSTRIDER BALLISTARII units have
    # Stealth).
    __tablename__ = "detachment_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    detachment_id: Mapped[int] = mapped_column(ForeignKey("detachments.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # No options means it applies to every unit.
    keyword_option_links: Mapped[list["DetachmentRuleKeywordOption"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    weapon_ability_grants: Mapped[list["DetachmentRuleWeaponAbility"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    datasheet_ability_grants: Mapped[list["DetachmentRuleDatasheetAbility"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    per_model_link: Mapped["DetachmentRulePerModel | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    # Keywords it gives the models it reaches (e.g. Houndpack Lance: WAR DOG
    # units have BATTLELINE).
    keyword_grant_links: Mapped[list["DetachmentRuleKeyword"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    selection_limit_link: Mapped["DetachmentRuleSelectionLimit | None"] = relationship(
        cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def selection_limit(self) -> int | None:
        # None: it reaches every matching unit. A number: it only reaches units
        # selected for it when building the list, up to that many per list
        # (e.g. Houndpack Lance: three WAR DOG units have CHARACTER).
        return self.selection_limit_link.limit if self.selection_limit_link else None

    @selection_limit.setter
    def selection_limit(self, limit: int | None) -> None:
        self.selection_limit_link = (
            DetachmentRuleSelectionLimit(limit=limit) if limit is not None else None
        )

    @property
    def granted_keywords(self) -> list["Keyword"]:
        return [link.keyword for link in self.keyword_grant_links]

    @granted_keywords.setter
    def granted_keywords(self, keywords: list["Keyword"]) -> None:
        self.keyword_grant_links = [DetachmentRuleKeyword(keyword=k) for k in keywords]

    @property
    def per_model(self) -> bool:
        # False: it reaches units whose every model matches one of its keyword
        # options (e.g. Stealth Optimisation - a unit only has Stealth if all
        # of it does). True: it reaches each matching model on its own, in any
        # unit (e.g. War-Form Mantles: "friendly TECH-PRIEST models have...").
        return self.per_model_link is not None

    @per_model.setter
    def per_model(self, per_model: bool) -> None:
        self.per_model_link = DetachmentRulePerModel() if per_model else None

    @property
    def keyword_options(self) -> list[list["Keyword"]]:
        # keyword_option_links grouped into their options; each option's
        # keywords are a set.
        options: dict[int, list[Keyword]] = {}
        for link in sorted(self.keyword_option_links, key=lambda link: link.option):
            options.setdefault(link.option, []).append(link.keyword)
        return list(options.values())

    @keyword_options.setter
    def keyword_options(self, options: list[list["Keyword"]]) -> None:
        self.keyword_option_links = [
            DetachmentRuleKeywordOption(option=i, keyword=keyword)
            for i, keywords in enumerate(options)
            for keyword in keywords
        ]


class DetachmentRuleKeywordOption(Base):
    # One keyword in one of a rule's keyword options; `option` numbers them.
    __tablename__ = "detachment_rule_keyword_options"

    rule_id: Mapped[int] = mapped_column(ForeignKey("detachment_rules.id"), primary_key=True)
    option: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)

    keyword: Mapped["Keyword"] = relationship(lazy="selectin")


class DetachmentRuleWeaponAbility(Base):
    # A weapon ability a rule gives the weapons of the units it applies to -
    # all of them, or only "ranged" or "melee" ones.
    __tablename__ = "detachment_rule_weapon_abilities"

    rule_id: Mapped[int] = mapped_column(ForeignKey("detachment_rules.id"), primary_key=True)
    weapon_ability_id: Mapped[int] = mapped_column(
        ForeignKey("weapon_abilities.id"), primary_key=True
    )
    weapon_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    weapon_ability: Mapped["WeaponAbility"] = relationship(lazy="selectin")


class DetachmentRuleDatasheetAbility(Base):
    # A datasheet ability a rule gives the units it applies to (e.g. Stealth).
    __tablename__ = "detachment_rule_datasheet_abilities"

    rule_id: Mapped[int] = mapped_column(ForeignKey("detachment_rules.id"), primary_key=True)
    datasheet_ability_id: Mapped[int] = mapped_column(
        ForeignKey("datasheet_abilities.id"), primary_key=True
    )

    datasheet_ability: Mapped["DatasheetAbility"] = relationship(lazy="selectin")


class DetachmentRuleKeyword(Base):
    # A keyword a rule gives the models it reaches.
    __tablename__ = "detachment_rule_keyword_grants"

    rule_id: Mapped[int] = mapped_column(ForeignKey("detachment_rules.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)

    keyword: Mapped["Keyword"] = relationship(lazy="selectin")


class DetachmentRuleSelectionLimit(Base):
    # How many units of a list can be selected for a rule (see
    # DetachmentRule.selection_limit). Its own table rather than a column, so
    # existing databases pick it up without a migration.
    __tablename__ = "detachment_rule_selection_limits"

    rule_id: Mapped[int] = mapped_column(ForeignKey("detachment_rules.id"), primary_key=True)
    limit: Mapped[int] = mapped_column(Integer)


class DetachmentRulePerModel(Base):
    # Marks a rule as reaching models one at a time (see DetachmentRule.per_model).
    # Its own table rather than a column, so existing databases pick it up
    # without a migration.
    __tablename__ = "detachment_rule_per_model"

    rule_id: Mapped[int] = mapped_column(ForeignKey("detachment_rules.id"), primary_key=True)
