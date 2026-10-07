from sqlalchemy import Column, ForeignKey, Table

from app.models.base import Base

datasheet_ability_links = Table(
    "datasheet_ability_links",
    Base.metadata,
    Column("model_id", ForeignKey("models.id"), primary_key=True),
    Column("datasheet_ability_id", ForeignKey("datasheet_abilities.id"), primary_key=True),
)

weapon_ability_links = Table(
    "weapon_ability_links",
    Base.metadata,
    Column("weapon_id", ForeignKey("weapons.id"), primary_key=True),
    Column("weapon_ability_id", ForeignKey("weapon_abilities.id"), primary_key=True),
)

unit_model_weapons = Table(
    "unit_model_weapons",
    Base.metadata,
    Column("unit_model_id", ForeignKey("unit_models.id"), primary_key=True),
    Column("weapon_id", ForeignKey("weapons.id"), primary_key=True),
)

unit_model_wargear = Table(
    "unit_model_wargear",
    Base.metadata,
    Column("unit_model_id", ForeignKey("unit_models.id"), primary_key=True),
    Column("wargear_id", ForeignKey("wargear.id"), primary_key=True),
)

detachment_dispositions = Table(
    "detachment_dispositions",
    Base.metadata,
    Column("detachment_id", ForeignKey("detachments.id"), primary_key=True),
    Column("disposition_id", ForeignKey("dispositions.id"), primary_key=True),
)

list_detachments = Table(
    "list_detachments",
    Base.metadata,
    Column("list_id", ForeignKey("lists.id"), primary_key=True),
    Column("detachment_id", ForeignKey("detachments.id"), primary_key=True),
)
