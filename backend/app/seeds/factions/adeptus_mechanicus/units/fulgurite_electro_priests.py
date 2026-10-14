from app.seeds.datasheets import ModelSpec, WeaponSpec

NAME = "Fulgurite Electro-priests"

MODELS = [
    ModelSpec(
        name="Fulgurite Electro-priest",
        movement=6,
        toughness=3,
        save=7,
        wounds=1,
        leadership=7,
        oc=1,
        invulnerable=5,
        feel_no_pain=5,
        keywords=("INFANTRY", "IMPERIUM", "CULT MECHANICUS", "ELECTRO-PRIESTS", "FULGURITE"),
        faction_abilities=("Doctrina Imperatives",),
        abilities=("Electro-infusion",),
        weapons=(
            WeaponSpec(
                name="Electroleech stave",
                weapon_type="melee",
                attacks="2",
                skill=3,
                strength=6,
                ap=-1,
                damage="2",
                abilities=("Devastating Wounds",),
            ),
        ),
    ),
]
