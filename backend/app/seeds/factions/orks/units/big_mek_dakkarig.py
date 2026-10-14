from app.seeds.datasheets import ModelSpec, WeaponSpec

NAME = "Big Mek Dakkarig"

MODELS = [
    ModelSpec(
        name="Big Mek Dakkarig",
        movement=8,
        toughness=8,
        save=3,
        wounds=11,
        leadership=7,
        oc=3,
        invulnerable=5,
        keywords=("VEHICLE", "BIG MEK", "CHARACTER", "WALKER"),
        faction_abilities=("Waaagh!",),
        # Even More Dakka: if this unit is riled up, its ranged attacks have
        # [SUSTAINED HITS 1].
        abilities=("Even More Dakka",),
        weapons=(
            WeaponSpec(
                name="Blitzkannon",
                weapon_type="ranged",
                range=24,
                attacks="8",
                skill=4,
                strength=7,
                ap=-2,
                damage="2",
                # Blitz Dem Gitz!: in your Shooting phase, against a unit that
                # isn't MONSTER/VEHICLE, this weapon has +6 A.
                abilities=("Ignores Cover", "Lethal Hits: non-Monster/Vehicle", "Blitz Dem Gitz!"),
            ),
            WeaponSpec(
                name="Multi-busta Launcha",
                weapon_type="ranged",
                range=24,
                attacks="6",
                skill=5,
                strength=10,
                ap=-2,
                damage="3",
                abilities=("Ignores Cover", "Lethal Hits"),
            ),
            WeaponSpec(
                name="Stompy Feet",
                weapon_type="melee",
                attacks="4",
                skill=3,
                strength=6,
                ap=-1,
                damage="1",
            ),
        ),
    ),
]
