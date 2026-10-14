from app.seeds.datasheets import ModelSpec, WargearSpec, WeaponSpec

NAME = "Skitarii Rangers"

MECHANICUS_PISTOL = WeaponSpec(
    name="Mechanicus pistol",
    weapon_type="ranged",
    range=12,
    attacks="1",
    skill=4,
    strength=6,
    ap=-1,
    damage="1",
    abilities=("Devastating Wounds", "Pistol"),
)
ARC_RIFLE = WeaponSpec(
    name="Arc rifle",
    weapon_type="ranged",
    range=30,
    attacks="1",
    skill=4,
    strength=8,
    ap=-1,
    damage="D3",
    abilities=("Anti-Vehicle 4+", "Devastating Wounds", "Rapid Fire 1"),
)
GALVANIC_RIFLE = WeaponSpec(
    name="Galvanic rifle",
    weapon_type="ranged",
    range=30,
    attacks="2",
    skill=4,
    strength=4,
    ap=0,
    damage="1",
)
PLASMA_CALIVER_STANDARD = WeaponSpec(
    name="Plasma caliver – standard",
    weapon_type="ranged",
    range=30,
    attacks="2",
    skill=4,
    strength=7,
    ap=-2,
    damage="1",
)
PLASMA_CALIVER_SUPERCHARGE = WeaponSpec(
    name="Plasma caliver – supercharge",
    weapon_type="ranged",
    range=30,
    attacks="2",
    skill=4,
    strength=8,
    ap=-3,
    damage="2",
    abilities=("Hazardous",),
)
TRANSURANIC_ARQUEBUS = WeaponSpec(
    name="Transuranic arquebus",
    weapon_type="ranged",
    range=36,
    attacks="1",
    skill=4,
    strength=7,
    ap=-2,
    damage="D3",
    abilities=("Heavy", "Precision"),
)
ALPHA_COMBAT_WEAPON = WeaponSpec(
    name="Alpha combat weapon",
    weapon_type="melee",
    attacks="2",
    skill=4,
    strength=5,
    ap=-1,
    damage="1",
)
CLOSE_COMBAT_WEAPON = WeaponSpec(
    name="Close combat weapon",
    weapon_type="melee",
    attacks="1",
    skill=4,
    strength=3,
    ap=0,
    damage="1",
)

OMNISPEX = WargearSpec(
    name="Omnispex",
    description=(
        "Ranged weapons equipped by models in the bearer's unit have the "
        "[IGNORES COVER] ability."
    ),
    abilities=("Ignore Cover (Unit)",),
)

# Rangers and their Alpha share a profile; they differ only in what they can
# be equipped with.
PROFILE = dict(
    movement=6,
    toughness=3,
    save=4,
    wounds=1,
    leadership=7,
    oc=2,
    invulnerable=5,
    keywords=(
        "INFANTRY",
        "BATTLELINE",
        "IMPERIUM",
        "ADEPTUS MECHANICUS",
        "SKITARII",
        "RANGERS",
    ),
    faction_abilities=("Doctrina Imperatives",),
)

MODELS = [
    ModelSpec(
        name="Skitarii Ranger",
        **PROFILE,
        weapons=(
            ARC_RIFLE,
            GALVANIC_RIFLE,
            PLASMA_CALIVER_STANDARD,
            PLASMA_CALIVER_SUPERCHARGE,
            TRANSURANIC_ARQUEBUS,
            CLOSE_COMBAT_WEAPON,
        ),
        wargear=(OMNISPEX,),
    ),
    ModelSpec(
        name="Skitarii Ranger Alpha",
        **PROFILE,
        weapons=(
            GALVANIC_RIFLE,
            CLOSE_COMBAT_WEAPON,
            ALPHA_COMBAT_WEAPON,
            MECHANICUS_PISTOL,
        ),
    ),
]
