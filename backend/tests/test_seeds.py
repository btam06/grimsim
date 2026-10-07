from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Detachment, Disposition, Faction, FactionUnit
from app.seeds import dispositions, factions, run_all
from app.seeds.detachments import adeptus_mechanicus as adeptus_mechanicus_detachments
from app.seeds.faction_units import adeptus_mechanicus


async def test_seed_dispositions_inserts_all_names(session: AsyncSession):
    await dispositions.seed(session)

    result = await session.execute(select(Disposition.name))
    names = set(result.scalars().all())
    assert names == set(dispositions.NAMES)


async def test_seed_dispositions_is_idempotent(session: AsyncSession):
    await dispositions.seed(session)
    await dispositions.seed(session)

    result = await session.execute(select(Disposition.name))
    names = result.scalars().all()
    assert len(names) == len(dispositions.NAMES)


async def test_seed_factions_inserts_all_names(session: AsyncSession):
    await factions.seed(session)

    result = await session.execute(select(Faction.name))
    names = set(result.scalars().all())
    assert names == set(factions.NAMES)


async def test_seed_factions_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await factions.seed(session)

    result = await session.execute(select(Faction.name))
    names = result.scalars().all()
    assert len(names) == len(factions.NAMES)


async def test_seed_factions_does_not_duplicate_existing(session: AsyncSession, faction_id: int):
    await factions.seed(session)

    result = await session.execute(select(Faction.name))
    names = result.scalars().all()
    assert len(names) == len(factions.NAMES) + 1


async def test_seed_adeptus_mechanicus_units_has_no_duplicate_names():
    assert len(adeptus_mechanicus.NAMES) == len(set(adeptus_mechanicus.NAMES))


async def test_seed_adeptus_mechanicus_units_inserts_all_names(session: AsyncSession):
    await factions.seed(session)
    await adeptus_mechanicus.seed(session)

    result = await session.execute(select(FactionUnit.name))
    names = set(result.scalars().all())
    assert names == set(adeptus_mechanicus.NAMES)


async def test_seed_adeptus_mechanicus_units_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await adeptus_mechanicus.seed(session)
    await adeptus_mechanicus.seed(session)

    result = await session.execute(select(FactionUnit.name))
    names = result.scalars().all()
    assert len(names) == len(adeptus_mechanicus.NAMES)


async def test_seed_adeptus_mechanicus_units_skips_if_faction_missing(session: AsyncSession):
    await adeptus_mechanicus.seed(session)

    result = await session.execute(select(FactionUnit.name))
    assert result.scalars().all() == []


async def test_seed_adeptus_mechanicus_detachments_has_no_duplicate_names():
    names = [name for name, _, _ in adeptus_mechanicus_detachments.ENTRIES]
    assert len(names) == len(set(names))


async def test_seed_adeptus_mechanicus_detachments_inserts_all_entries(session: AsyncSession):
    await dispositions.seed(session)
    await factions.seed(session)
    await adeptus_mechanicus_detachments.seed(session)

    result = await session.execute(
        select(Detachment).options(selectinload(Detachment.dispositions))
    )
    detachments = result.scalars().all()
    names = {d.name for d in detachments}
    assert names == {name for name, _, _ in adeptus_mechanicus_detachments.ENTRIES}

    dp_by_name = {name: dp for name, _, dp in adeptus_mechanicus_detachments.ENTRIES}
    disposition_by_name = {
        name: disposition_name for name, disposition_name, _ in adeptus_mechanicus_detachments.ENTRIES
    }
    for d in detachments:
        assert d.dp == dp_by_name[d.name]
        assert [disp.name for disp in d.dispositions] == [disposition_by_name[d.name]]


async def test_seed_adeptus_mechanicus_detachments_is_idempotent(session: AsyncSession):
    await dispositions.seed(session)
    await factions.seed(session)
    await adeptus_mechanicus_detachments.seed(session)
    await adeptus_mechanicus_detachments.seed(session)

    result = await session.execute(select(Detachment.name))
    names = result.scalars().all()
    assert len(names) == len(adeptus_mechanicus_detachments.ENTRIES)


async def test_seed_adeptus_mechanicus_detachments_skips_if_faction_missing(
    session: AsyncSession,
):
    await dispositions.seed(session)
    await adeptus_mechanicus_detachments.seed(session)

    result = await session.execute(select(Detachment.name))
    assert result.scalars().all() == []


async def test_run_all_seeds_everything(session: AsyncSession):
    await run_all(session)

    disposition_names = set((await session.execute(select(Disposition.name))).scalars().all())
    faction_names = set((await session.execute(select(Faction.name))).scalars().all())
    faction_unit_names = set((await session.execute(select(FactionUnit.name))).scalars().all())
    detachment_names = set((await session.execute(select(Detachment.name))).scalars().all())
    assert disposition_names == set(dispositions.NAMES)
    assert faction_names == set(factions.NAMES)
    assert faction_unit_names == set(adeptus_mechanicus.NAMES)
    assert detachment_names == {name for name, _, _ in adeptus_mechanicus_detachments.ENTRIES}
