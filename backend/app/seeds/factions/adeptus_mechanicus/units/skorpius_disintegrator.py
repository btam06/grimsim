from app.seeds.datasheets import ModelSpec, WeaponSpec

NAME = "Skorpius Disintegrator"

COGNIS_HEAVY_STUBBER = WeaponSpec(
    name="Cognis heavy stubber",
    weapon_type="ranged",
    range=36,
    attacks="3",
    skill=4,
    strength=4,
    ap=0,
    damage="1",
    abilities=("Rapid Fire 3", "Sustained 1"),
)

MODELS = [
    ModelSpec(
        name="Skorpius Disintegrator",
        movement=10,
        toughness=10,
        save=2,
        wounds=12,
        leadership=7,
        oc=3,
        keywords=(
            "VEHICLE",
            "IMPERIUM",
            "FRAME",
            "SKITARII",
            "SMOKE",
            "SKORPIUS DISINTEGRATOR",
        ),
        faction_abilities=("Doctrina Imperatives",),
        # Blistering Salvoes is on the two cannons as weapon abilities, since
        # each half applies to one weapon only.
        abilities=("Deadly Demise D3", "Broad Spectrum Data-tether"),
        weapons=(
            WeaponSpec(
                name="Belleros energy cannon",
                weapon_type="ranged",
                range=36,
                attacks="2D6",
                skill=4,
                strength=7,
                ap=-2,
                damage="1",
                abilities=("Blast", "Indirect Fire", "Blistering Salvoes: Infantry"),
            ),
            # Three of these, each fired separately.
            COGNIS_HEAVY_STUBBER,
            COGNIS_HEAVY_STUBBER,
            COGNIS_HEAVY_STUBBER,
            WeaponSpec(
                name="Disruptor missile launcher",
                weapon_type="ranged",
                range=36,
                attacks="3",
                skill=4,
                strength=9,
                ap=-2,
                damage="D6",
                abilities=("Twin-linked",),
            ),
            WeaponSpec(
                name="Ferrumite cannon",
                weapon_type="ranged",
                range=48,
                attacks="3",
                skill=4,
                strength=12,
                ap=-3,
                damage="D6+1",
                abilities=("Blistering Salvoes: Monster/Vehicle",),
            ),
            WeaponSpec(
                name="Armoured hull",
                weapon_type="melee",
                attacks="3",
                skill=4,
                strength=6,
                ap=0,
                damage="1",
            ),
        ),
    ),
]
