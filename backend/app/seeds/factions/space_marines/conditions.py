# Space Marines conditions - checks for its own rules, shaped like the core
# ones in app/combat_rules/conditions.py, which combines them. Rules combine
# them with core conditions (e.g. Terminatus Assault: CRITICAL_HIT, CHARGED,
# LIGHTNING_CLAWS_WEAPON and TARGET_NOT_MONSTER_OR_VEHICLE).

LIGHTNING_CLAWS_WEAPON = "lightning_claws_weapon"
THUNDER_HAMMER_WEAPON = "thunder_hammer_weapon"
ASSAULT_DOCTRINE_ACTIVE = "assault_doctrine_active"
DEVASTATOR_DOCTRINE_ACTIVE = "devastator_doctrine_active"
TACTICAL_DOCTRINE_ACTIVE = "tactical_doctrine_active"
CALGARS_CHAMPION_ATTACK = "calgars_champion_attack"
TARGET_MODEL_OTHER_CHARACTER = "target_model_other_character"
MELEE_PRE_WEAPON = "melee_pre_weapon"
PSYCHIC_ATTACK = "psychic_attack"


def _weapon(context: dict, name: str) -> bool:
    return name in context.get("weapon_name", "").lower()


def lightning_claws_weapon(context: dict) -> bool:
    # The attack is made with a Lightning Claws weapon - e.g. Terminatus
    # Assault.
    return _weapon(context, "lightning claws")


def thunder_hammer_weapon(context: dict) -> bool:
    # As lightning_claws_weapon, for a Thunder Hammer weapon.
    return _weapon(context, "thunder hammer")


def _doctrine(context: dict, name: str) -> bool:
    return f"{name} Doctrine" in context.get("attacker_options", set())


def assault_doctrine_active(context: dict) -> bool:
    # The attacking unit has the Assault Doctrine active (Combat Doctrines) -
    # e.g. Gene-Wrought Might's +1 AP, Purgatus Tactics.
    return _doctrine(context, "Assault")


def devastator_doctrine_active(context: dict) -> bool:
    # As assault_doctrine_active, for the Devastator Doctrine - e.g. Furor
    # Tactics.
    return _doctrine(context, "Devastator")


def tactical_doctrine_active(context: dict) -> bool:
    # As assault_doctrine_active, for the Tactical Doctrine - e.g. Malleus
    # Tactics.
    return _doctrine(context, "Tactical")


def calgars_champion_attack(context: dict) -> bool:
    # An attack by the model with Calgar's Champion (not its unit's other
    # models), against a unit with a CHARACTER model.
    return "Calgar's Champion" in context.get(
        "attacker_model_abilities", set()
    ) and "CHARACTER" in context.get("defender_keywords", set())


def target_model_other_character(context: dict) -> bool:
    # A defending CHARACTER model other than the one with Veteran Bodyguard
    # (checked per model, as its profile's worked out).
    return (
        context.get("step") == "target_model"
        and "CHARACTER" in context.get("target_model_keywords", set())
        and "Veteran Bodyguard" not in context.get("target_model_abilities", set())
    )


def melee_pre_weapon(context: dict) -> bool:
    # Checked once per melee weapon - e.g. for "+1 A" to melee attacks.
    return context.get("step") == "pre_weapon" and not context.get("is_ranged", True)


def psychic_attack(context: dict) -> bool:
    # An attack made with a [PSYCHIC] weapon - e.g. Psychic Hood's Feel No Pain.
    return "Psychic" in context.get("weapon_ability_names", set())


CONDITIONS = {
    PSYCHIC_ATTACK: psychic_attack,
    CALGARS_CHAMPION_ATTACK: calgars_champion_attack,
    TARGET_MODEL_OTHER_CHARACTER: target_model_other_character,
    MELEE_PRE_WEAPON: melee_pre_weapon,
    LIGHTNING_CLAWS_WEAPON: lightning_claws_weapon,
    THUNDER_HAMMER_WEAPON: thunder_hammer_weapon,
    ASSAULT_DOCTRINE_ACTIVE: assault_doctrine_active,
    DEVASTATOR_DOCTRINE_ACTIVE: devastator_doctrine_active,
    TACTICAL_DOCTRINE_ACTIVE: tactical_doctrine_active,
}
