from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Faction, FactionAbility

# (faction name, ability name, description) - one hardcoded, faction-wide
# special rule per faction. These are descriptive only: unlike WeaponAbility/
# WargearAbility/DatasheetAbility, a FactionAbility has no conditions/effects
# for the combat engine to key off.
ENTRIES = [
    (
        "Adeptus Sororitas",
        "Acts of Faith",
        "Units can call upon Acts of Faith, fuelled by the army's Devotion, for timely miracles.",
    ),
    (
        "Adeptus Custodes",
        "Martial Ka'tah",
        "Units can adopt a Ka'tah stance in the Fight phase, granting a tailored combat bonus.",
    ),
    (
        "Adeptus Mechanicus",
        "Doctrina Imperatives",
        "Units can be affected by a Doctrina Imperative, improving their hit rolls, Toughness, or invulnerable save.",
    ),
    (
        "Astra Militarum",
        "Voice of Command",
        "Officers can issue Orders to nearby friendly units, granting a temporary tactical bonus.",
    ),
    (
        "Grey Knights",
        "Teleport Strike",
        "Units can arrive on the battlefield via deep strike, teleporting in close to the enemy.",
    ),
    (
        "Imperial Agents",
        "Agents of the Imperium",
        "Units may be included in an allied Imperium army if every model in that army has the IMPERIUM keyword.",
    ),
    (
        "Imperial Knights",
        "Household Choice",
        "The army pledges itself to a Knight Household, granting a bonus ability that reflects its traditions.",
    ),
    (
        "Space Marines",
        "Oath of Moment",
        "The army designates one enemy unit as the target of its Oath of Moment, improving rolls against it.",
    ),
    (
        "Chaos Daemons",
        "Daemonic Ritual",
        "The army can perform Daemonic Rituals to summon additional Daemons onto the battlefield.",
    ),
    (
        "Chaos Knights",
        "Favoured Household",
        "The army pledges itself to a traitor Knight Household, granting a bonus ability in return for loyalty.",
    ),
    (
        "Chaos Space Marines",
        "Dark Pacts",
        "Units can invoke a Dark Pact for a one-use bonus, at the cost of a self-inflicted price.",
    ),
    (
        "Death Guard",
        "Disgustingly Resilient",
        "Units can shrug off wounds that would fell a lesser warrior, courtesy of Nurgle's gifts.",
    ),
    (
        "Emperor's Children",
        "Excess of Violence",
        "Units are driven into a heightened state by the thrill of battle, rewarding excess and spectacle.",
    ),
    (
        "Thousand Sons",
        "Cabalistic Rituals",
        "The army's sorcerers can perform Cabalistic Rituals to empower their psychic workings.",
    ),
    (
        "World Eaters",
        "Blood Tithe",
        "The army accrues Blood Tithe points from kills, spending them to unleash brutal bonuses.",
    ),
    (
        "Aeldari",
        "Strands of Fate",
        "The army can spend Fate dice to manipulate the strands of fate, re-rolling crucial rolls.",
    ),
    (
        "Drukhari",
        "Power from Pain",
        "Units grow more lethal as the battle wears on, fuelled by the suffering they inflict.",
    ),
    (
        "Genestealer Cults",
        "Cult Ambush",
        "Units can lie in wait and burst from hiding via tunnels, ambushing the enemy from close range.",
    ),
    (
        "Leagues of Votann",
        "Hearthkyn Oaths",
        "The army swears a Hearthkyn Oath before battle, granting a bonus that reflects its chosen creed.",
    ),
    (
        "Necrons",
        "Reanimation Protocols",
        "Destroyed models can attempt to reanimate at the end of the turn, rising again to fight on.",
    ),
    (
        "Orks",
        "Waaagh!",
        "The army can call a Waaagh!, surging forward with a momentum bonus for a turn.",
    ),
    (
        "T'au Empire",
        "Mont'ka and Kauyon",
        "The army adopts the tactic of Mont'ka (the killing blow) or Kauyon (the patient hunter) for a battle round.",
    ),
    (
        "Tyranids",
        "Synapse",
        "Synapse creatures hold lesser broods in their psychic thrall, keeping them fighting at their best.",
    ),
]


async def seed(session: AsyncSession) -> None:
    factions_by_name = {
        faction.name: faction.id
        for faction in (await session.execute(select(Faction))).scalars().all()
    }
    existing = {
        (faction_id, name)
        for faction_id, name in (
            await session.execute(select(FactionAbility.faction_id, FactionAbility.name))
        ).all()
    }

    missing = []
    for faction_name, ability_name, description in ENTRIES:
        faction_id = factions_by_name.get(faction_name)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        if (faction_id, ability_name) in existing:
            continue
        missing.append(
            FactionAbility(name=ability_name, description=description, faction_id=faction_id)
        )

    if missing:
        session.add_all(missing)
        await session.commit()
