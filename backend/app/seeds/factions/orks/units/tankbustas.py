from app.seeds.datasheets import ModelSpec, WeaponSpec

NAME = "Tankbustas"

# Each "- Standard"/"- Hunter" pair is one weapon with two profiles: before
# attacking, one of its eligible profiles is selected. Hunter profiles can only
# target units with the specified keywords.
TANKBUSTA_WEAPONS = (
    WeaponSpec(
        name="Busta Rokkit Launcha - Standard",
        weapon_type="ranged",
        range=24,
        attacks="2",
        skill=4,
        strength=10,
        ap=-2,
        damage="3",
    ),
    WeaponSpec(
        name="Busta Rokkit Launcha - Hunter",
        weapon_type="ranged",
        range=24,
        attacks="3",
        skill=4,
        strength=12,
        ap=-2,
        damage="3",
        abilities=("Hunter: Monster/Vehicle",),
    ),
    WeaponSpec(
        name="Gitstikka",
        weapon_type="melee",
        attacks="3",
        skill=3,
        strength=5,
        ap=0,
        damage="1",
    ),
)

NOB_WEAPONS = (
    WeaponSpec(
        name="Rokkit Pistol",
        weapon_type="ranged",
        range=12,
        attacks="1",
        skill=4,
        strength=10,
        ap=-2,
        damage="3",
        abilities=("Close-Quarters",),
    ),
    WeaponSpec(
        name="Choppa",
        weapon_type="melee",
        attacks="4",
        skill=3,
        strength=5,
        ap=-1,
        damage="1",
    ),
    WeaponSpec(
        name="Smash Hammer - Standard",
        weapon_type="melee",
        attacks="3",
        skill=3,
        strength=7,
        ap=-2,
        damage="2",
    ),
    WeaponSpec(
        name="Smash Hammer - Hunter",
        weapon_type="melee",
        attacks="3",
        skill=3,
        strength=12,
        ap=-2,
        damage="3",
        abilities=("Hunter: Monster/Vehicle",),
    ),
)

KEYWORDS = ("INFANTRY", "EXPLOSIVES")

MODELS = [
    ModelSpec(
        name="Tankbusta",
        movement=6,
        toughness=5,
        save=4,
        wounds=2,
        leadership=7,
        oc=1,
        keywords=KEYWORDS,
        faction_abilities=("Waaagh!",),
        weapons=TANKBUSTA_WEAPONS,
    ),
    ModelSpec(
        name="Tankbusta Nob",
        movement=6,
        toughness=5,
        save=4,
        wounds=3,
        leadership=7,
        oc=1,
        keywords=KEYWORDS,
        faction_abilities=("Waaagh!",),
        weapons=NOB_WEAPONS,
    ),
]
