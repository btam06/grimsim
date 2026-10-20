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

weapon_ability_conditions = Table(
    "weapon_ability_conditions",
    Base.metadata,
    Column("weapon_ability_id", ForeignKey("weapon_abilities.id"), primary_key=True),
    Column("condition_id", ForeignKey("conditions.id"), primary_key=True),
)

weapon_ability_effects = Table(
    "weapon_ability_effects",
    Base.metadata,
    Column("weapon_ability_id", ForeignKey("weapon_abilities.id"), primary_key=True),
    Column("effect_id", ForeignKey("effects.id"), primary_key=True),
)

wargear_ability_links = Table(
    "wargear_ability_links",
    Base.metadata,
    Column("wargear_id", ForeignKey("wargear.id"), primary_key=True),
    Column("wargear_ability_id", ForeignKey("wargear_abilities.id"), primary_key=True),
)

wargear_ability_conditions = Table(
    "wargear_ability_conditions",
    Base.metadata,
    Column("wargear_ability_id", ForeignKey("wargear_abilities.id"), primary_key=True),
    Column("condition_id", ForeignKey("conditions.id"), primary_key=True),
)

wargear_ability_effects = Table(
    "wargear_ability_effects",
    Base.metadata,
    Column("wargear_ability_id", ForeignKey("wargear_abilities.id"), primary_key=True),
    Column("effect_id", ForeignKey("effects.id"), primary_key=True),
)

model_keyword_links = Table(
    "model_keyword_links",
    Base.metadata,
    Column("model_id", ForeignKey("models.id"), primary_key=True),
    Column("keyword_id", ForeignKey("keywords.id"), primary_key=True),
)

datasheet_ability_conditions = Table(
    "datasheet_ability_conditions",
    Base.metadata,
    Column("datasheet_ability_id", ForeignKey("datasheet_abilities.id"), primary_key=True),
    Column("condition_id", ForeignKey("conditions.id"), primary_key=True),
)

datasheet_ability_effects = Table(
    "datasheet_ability_effects",
    Base.metadata,
    Column("datasheet_ability_id", ForeignKey("datasheet_abilities.id"), primary_key=True),
    Column("effect_id", ForeignKey("effects.id"), primary_key=True),
)

stratagem_detachments = Table(
    "stratagem_detachments",
    Base.metadata,
    Column("stratagem_id", ForeignKey("stratagems.id"), primary_key=True),
    Column("detachment_id", ForeignKey("detachments.id"), primary_key=True),
)

stratagem_conditions = Table(
    "stratagem_conditions",
    Base.metadata,
    Column("stratagem_id", ForeignKey("stratagems.id"), primary_key=True),
    Column("condition_id", ForeignKey("conditions.id"), primary_key=True),
)

stratagem_effects = Table(
    "stratagem_effects",
    Base.metadata,
    Column("stratagem_id", ForeignKey("stratagems.id"), primary_key=True),
    Column("effect_id", ForeignKey("effects.id"), primary_key=True),
)

model_faction_ability_links = Table(
    "model_faction_ability_links",
    Base.metadata,
    Column("model_id", ForeignKey("models.id"), primary_key=True),
    Column("faction_ability_id", ForeignKey("faction_abilities.id"), primary_key=True),
)

stratagem_keywords = Table(
    "stratagem_keywords",
    Base.metadata,
    Column("stratagem_id", ForeignKey("stratagems.id"), primary_key=True),
    Column("keyword_id", ForeignKey("keywords.id"), primary_key=True),
)

# Keywords that stop a stratagem applying to a model (e.g. VEHICLE for Baleful
# Halo's "excluding VEHICLE units").
stratagem_excluded_keywords = Table(
    "stratagem_excluded_keywords",
    Base.metadata,
    Column("stratagem_id", ForeignKey("stratagems.id"), primary_key=True),
    Column("keyword_id", ForeignKey("keywords.id"), primary_key=True),
)

# A list's owner (at most one user per list). A link table rather than a
# column on lists, so existing databases pick it up without a migration.
list_owners = Table(
    "list_owners",
    Base.metadata,
    Column("list_id", ForeignKey("lists.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), nullable=False),
)

# Keywords an enhancement or upgrade needs (all of them) on the model carrying
# it (enhancements) or every model in the unit (upgrades), and keywords that
# rule it out (any one of them).
enhancement_keywords = Table(
    "enhancement_keywords",
    Base.metadata,
    Column("enhancement_id", ForeignKey("enhancements.id"), primary_key=True),
    Column("keyword_id", ForeignKey("keywords.id"), primary_key=True),
)

enhancement_excluded_keywords = Table(
    "enhancement_excluded_keywords",
    Base.metadata,
    Column("enhancement_id", ForeignKey("enhancements.id"), primary_key=True),
    Column("keyword_id", ForeignKey("keywords.id"), primary_key=True),
)

# The enhancement a model in a unit carries (at most one per model).
unit_model_enhancements = Table(
    "unit_model_enhancements",
    Base.metadata,
    Column("unit_model_id", ForeignKey("unit_models.id"), primary_key=True),
    Column("enhancement_id", ForeignKey("enhancements.id")),
)

# The upgrade a unit has (at most one per unit).
unit_upgrades = Table(
    "unit_upgrades",
    Base.metadata,
    Column("unit_id", ForeignKey("units.id"), primary_key=True),
    Column("enhancement_id", ForeignKey("enhancements.id")),
)

# The base size a model is on (at most one per model).
model_base_sizes = Table(
    "model_base_sizes",
    Base.metadata,
    Column("model_id", ForeignKey("models.id"), primary_key=True),
    Column("base_size_id", ForeignKey("base_sizes.id")),
)
