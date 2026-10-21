from app.combat_rules.conditions import attacker_is_battleline, target_led_by_character

# Adeptus Mechanicus conditions - checks for its own rules (e.g. Doctrina
# Imperatives, Breaching Command, Murderous Imperative), shaped like the core
# ones in app/combat_rules/conditions.py, which combines them.

MELEE_ATTACK_AGAINST_BATTLELINE = "melee_attack_against_battleline"
ATTACKER_NEAR_ADMECH_BATTLELINE = "attacker_near_admech_battleline"
ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE = "attacker_battleline_or_near_admech_battleline"
MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE = "melee_vs_battleline_or_near_admech_battleline"
PROTECTOR_IMPERATIVE_ACTIVE = "protector_imperative_active"
CONQUEROR_IMPERATIVE_ACTIVE = "conqueror_imperative_active"
TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER = "target_electro_priests_led_by_character"
KASTELAN_RANGED_WEAPON = "kastelan_ranged_weapon"
KASTELAN_MELEE_WEAPON = "kastelan_melee_weapon"
TARGET_MODEL_KASTELAN = "target_model_kastelan"
TARGET_MODEL_DATASMITH_LEADING_KASTELANS = "target_model_datasmith_leading_kastelans"

# The calculator's Positioning: "within 6\" of a friendly ADEPTUS MECHANICUS
# BATTLELINE unit" (see app/combat_rules/positions.py).
NEAR_ADMECH_BATTLELINE = "near_admech_battleline"


def melee_attack_against_battleline(context: dict) -> bool:
    # True at the pre-hit check of a melee attack against a defending unit
    # that contains a BATTLELINE model (e.g. Protector Imperative's -1 to hit).
    return (
        context.get("step") == "pre_hit"
        and not context.get("is_ranged", True)
        and "BATTLELINE" in context.get("defender_keywords", set())
    )


def attacker_near_admech_battleline(context: dict) -> bool:
    # True at every step while the attacking unit is within 6" of a friendly
    # ADEPTUS MECHANICUS BATTLELINE unit (e.g. Breaching Command's re-rolls).
    return NEAR_ADMECH_BATTLELINE in context.get("attacker_positions", set())


def attacker_battleline_or_near_admech_battleline(context: dict) -> bool:
    # As attacker_is_battleline, or while the attacking unit is within 6" of a
    # friendly ADEPTUS MECHANICUS BATTLELINE unit (Conqueror Imperative).
    return attacker_is_battleline(context) or attacker_near_admech_battleline(context)


def melee_vs_battleline_or_near_admech_battleline(context: dict) -> bool:
    # As melee_attack_against_battleline, or against a defending unit within
    # 6" of a friendly ADEPTUS MECHANICUS BATTLELINE unit (Protector Imperative).
    return (
        context.get("step") == "pre_hit"
        and not context.get("is_ranged", True)
        and (
            "BATTLELINE" in context.get("defender_keywords", set())
            or NEAR_ADMECH_BATTLELINE in context.get("defender_positions", set())
        )
    )


def protector_imperative_active(context: dict) -> bool:
    # The attacking unit has the Protector Imperative active (picked under the
    # calculator's Faction Rules) - e.g. Murderous Imperative.
    return "Protector Imperative" in context.get("attacker_options", set())


def conqueror_imperative_active(context: dict) -> bool:
    # As protector_imperative_active, for the Conqueror Imperative.
    return "Conqueror Imperative" in context.get("attacker_options", set())


def target_electro_priests_led_by_character(context: dict) -> bool:
    # As target_led_by_character, for a led unit with the ELECTRO-PRIESTS keyword.
    return target_led_by_character(context) and "ELECTRO-PRIESTS" in context.get(
        "defender_keywords", set()
    )


def kastelan_ranged_weapon(context: dict) -> bool:
    # Checked once per weapon: a ranged weapon fired by a KASTELAN ROBOTS model
    # (e.g. the Protector Protocol's +2 Attacks).
    return (
        context.get("step") == "pre_weapon"
        and context.get("is_ranged", False)
        and "KASTELAN ROBOTS" in context.get("attacker_model_keywords", set())
    )


def kastelan_melee_weapon(context: dict) -> bool:
    # As kastelan_ranged_weapon, for melee weapons (the Conqueror Protocol).
    return (
        context.get("step") == "pre_weapon"
        and not context.get("is_ranged", True)
        and "KASTELAN ROBOTS" in context.get("attacker_model_keywords", set())
    )


def target_model_kastelan(context: dict) -> bool:
    # A defending KASTELAN ROBOTS model (checked per model - e.g. the Aegis
    # Protocol's +1 Toughness).
    return "KASTELAN ROBOTS" in context.get("target_model_keywords", set())


def target_model_datasmith_leading_kastelans(context: dict) -> bool:
    # A defending CYBERNETICA DATASMITH model in a unit with KASTELAN ROBOTS -
    # i.e. leading them (Robotic Bodyguard's Feel No Pain 4+).
    return "CYBERNETICA DATASMITH" in context.get(
        "target_model_keywords", set()
    ) and "KASTELAN ROBOTS" in context.get("defender_keywords", set())


# {keyword: check}
CONDITIONS = {
    MELEE_ATTACK_AGAINST_BATTLELINE: melee_attack_against_battleline,
    ATTACKER_NEAR_ADMECH_BATTLELINE: attacker_near_admech_battleline,
    ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE: attacker_battleline_or_near_admech_battleline,
    MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE: melee_vs_battleline_or_near_admech_battleline,
    PROTECTOR_IMPERATIVE_ACTIVE: protector_imperative_active,
    CONQUEROR_IMPERATIVE_ACTIVE: conqueror_imperative_active,
    TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER: target_electro_priests_led_by_character,
    KASTELAN_RANGED_WEAPON: kastelan_ranged_weapon,
    KASTELAN_MELEE_WEAPON: kastelan_melee_weapon,
    TARGET_MODEL_KASTELAN: target_model_kastelan,
    TARGET_MODEL_DATASMITH_LEADING_KASTELANS: target_model_datasmith_leading_kastelans,
}

# Seeded Condition rows: (keyword, name, description).
ENTRIES = [
    (
        MELEE_ATTACK_AGAINST_BATTLELINE,
        "Melee Attack Against Battleline",
        "A melee attack against a defending unit that contains a BATTLELINE model.",
    ),
    (
        ATTACKER_NEAR_ADMECH_BATTLELINE,
        "Attacker Near AdMech Battleline",
        "The attacking unit is within 6\" of a friendly ADEPTUS MECHANICUS BATTLELINE unit.",
    ),
    (
        ATTACKER_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
        "Attacker Battleline or Near AdMech Battleline",
        "The attacking unit is BATTLELINE, or within 6\" of a friendly ADEPTUS MECHANICUS "
        "BATTLELINE unit.",
    ),
    (
        MELEE_VS_BATTLELINE_OR_NEAR_ADMECH_BATTLELINE,
        "Melee Attack vs Battleline or Near AdMech Battleline",
        "A melee attack against a unit that is BATTLELINE, or within 6\" of a friendly "
        "ADEPTUS MECHANICUS BATTLELINE unit.",
    ),
    (
        PROTECTOR_IMPERATIVE_ACTIVE,
        "Protector Imperative Active",
        "The attacking unit has the Protector Imperative active.",
    ),
    (
        CONQUEROR_IMPERATIVE_ACTIVE,
        "Conqueror Imperative Active",
        "The attacking unit has the Conqueror Imperative active.",
    ),
    (
        TARGET_ELECTRO_PRIESTS_LED_BY_CHARACTER,
        "Target is Electro-priests Led by Character",
        "The defending unit is ELECTRO-PRIESTS led by a CHARACTER. Applies at every step.",
    ),
    (
        KASTELAN_RANGED_WEAPON,
        "Kastelan Ranged Weapon",
        "A ranged weapon fired by a KASTELAN ROBOTS model (checked once per weapon).",
    ),
    (
        KASTELAN_MELEE_WEAPON,
        "Kastelan Melee Weapon",
        "A melee weapon used by a KASTELAN ROBOTS model (checked once per weapon).",
    ),
    (
        TARGET_MODEL_KASTELAN,
        "Target Model is a Kastelan",
        "The defending model is a KASTELAN ROBOTS model.",
    ),
    (
        TARGET_MODEL_DATASMITH_LEADING_KASTELANS,
        "Target Model is a Datasmith Leading Kastelans",
        "The defending model is a CYBERNETICA DATASMITH in a unit with KASTELAN ROBOTS.",
    ),
]
