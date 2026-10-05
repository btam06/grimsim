from sqlalchemy import Column, ForeignKey, Table

from app.models.base import Base

datasheet_ability_links = Table(
    "datasheet_ability_links",
    Base.metadata,
    Column("model_id", ForeignKey("models.id"), primary_key=True),
    Column("datasheet_ability_id", ForeignKey("datasheet_abilities.id"), primary_key=True),
)

unit_models = Table(
    "unit_models",
    Base.metadata,
    Column("unit_id", ForeignKey("units.id"), primary_key=True),
    Column("model_id", ForeignKey("models.id"), primary_key=True),
)

weapon_ability_links = Table(
    "weapon_ability_links",
    Base.metadata,
    Column("weapon_id", ForeignKey("weapons.id"), primary_key=True),
    Column("weapon_ability_id", ForeignKey("weapon_abilities.id"), primary_key=True),
)
