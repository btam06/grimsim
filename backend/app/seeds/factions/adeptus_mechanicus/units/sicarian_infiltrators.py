from app.seeds.datasheets import ModelSpec, WeaponSpec

NAME = "Sicarian Infiltrators"

WEAPONS = (
    WeaponSpec(
        name="Flechette blaster pistol",
        weapon_type="ranged",
        range=12,
        attacks="5",
        skill=4,
        strength=3,
        ap=0,
        damage="1",
        abilities=("Pistol",),
    ),
    WeaponSpec(
        name="Stubcarbine pistol",
        weapon_type="ranged",
        range=12,
        attacks="3",
        skill=4,
        strength=4,
        ap=0,
        damage="1",
        abilities=("Pistol",),
    ),
    WeaponSpec(
        name="Power weapon",
        weapon_type="melee",
        attacks="4",
        skill=4,
        strength=4,
        ap=-2,
        damage="1",
    ),
    WeaponSpec(
        name="Taser goad",
        weapon_type="melee",
        attacks="3",
        skill=4,
        strength=6,
        ap=-1,
        damage="1",
        abilities=("Sustained 2",),
    ),
)

# Infiltrators and their Princeps share a profile and wargear options; only
# the name differs.
PROFILE = dict(
    movement=8,
    toughness=4,
    save=4,
    wounds=2,
    leadership=7,
    oc=1,
    invulnerable=5,
    keywords=("INFANTRY", "IMPERIUM", "SKITARII", "SICARIAN", "INFILTRATORS"),
    faction_abilities=("Doctrina Imperatives",),
    abilities=(
        "Infiltrators",
        "Stealth",
        "Voices in the Code",
        "Neurostatic Interference (Aura)",
    ),
    weapons=WEAPONS,
)

MODELS = [
    ModelSpec(name="Sicarian Infiltrator", **PROFILE),
    ModelSpec(name="Sicarian Infiltrator Princeps", **PROFILE),
]
