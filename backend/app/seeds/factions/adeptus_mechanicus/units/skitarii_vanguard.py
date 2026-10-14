from app.seeds.datasheets import ModelSpec, WeaponSpec
from app.seeds.factions.adeptus_mechanicus.units.skitarii_rangers import (
    ALPHA_COMBAT_WEAPON,
    ARC_RIFLE,
    CLOSE_COMBAT_WEAPON,
    MECHANICUS_PISTOL,
    OMNISPEX,
    PLASMA_CALIVER_STANDARD,
    PLASMA_CALIVER_SUPERCHARGE,
    PROFILE as RANGERS_PROFILE,
    TRANSURANIC_ARQUEBUS,
)

NAME = "Skitarii Vanguard"

# The same as Skitarii Rangers, but with radium carbines in place of galvanic
# rifles (and VANGUARD in place of the RANGERS keyword).
RADIUM_CARBINE = WeaponSpec(
    name="Radium carbine",
    weapon_type="ranged",
    range=18,
    attacks="3",
    skill=4,
    strength=3,
    ap=0,
    damage="1",
    abilities=("Anti-Infantry 4+",),
)

PROFILE = {
    **RANGERS_PROFILE,
    "keywords": tuple(
        "VANGUARD" if keyword == "RANGERS" else keyword
        for keyword in RANGERS_PROFILE["keywords"]
    ),
}

MODELS = [
    ModelSpec(
        name="Skitarii Vanguard",
        **PROFILE,
        weapons=(
            ARC_RIFLE,
            RADIUM_CARBINE,
            PLASMA_CALIVER_STANDARD,
            PLASMA_CALIVER_SUPERCHARGE,
            TRANSURANIC_ARQUEBUS,
            CLOSE_COMBAT_WEAPON,
        ),
        wargear=(OMNISPEX,),
    ),
    ModelSpec(
        name="Skitarii Vanguard Alpha",
        **PROFILE,
        weapons=(
            RADIUM_CARBINE,
            CLOSE_COMBAT_WEAPON,
            ALPHA_COMBAT_WEAPON,
            MECHANICUS_PISTOL,
        ),
    ),
]
