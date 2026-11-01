from __future__ import annotations

from dataclasses import fields

from app.engine import state
from app.engine.catalog import Catalog

# A game as the database holds it (the app.models Game and its rows) turned
# into its plain state (see app/engine/state.py), with the catalog rows it
# refers to copied into a Catalog. For games still played through the
# database: their autosaves (see app/engine/saves.py).

_classes = {
    cls.__name__: cls
    for cls in vars(state).values()
    if isinstance(cls, type) and issubclass(cls, state.State) and cls is not state.State
}


def from_orm(orm_game, catalog: Catalog | None = None) -> tuple[state.Game, Catalog]:
    catalog = catalog if catalog is not None else Catalog()
    return _record(orm_game, catalog), catalog


def _record(orm_obj, catalog: Catalog):
    cls = _classes[type(orm_obj).__name__]
    kwargs = {}
    for f in fields(cls):
        value = getattr(orm_obj, f.name)
        if f.name in cls._refs:
            value = catalog.add(value) if value is not None else None
        elif isinstance(value, list):
            value = [_record(v, catalog) if type(v).__name__ in _classes else v for v in value]
        elif value is not None and type(value).__name__ in _classes:
            value = _record(value, catalog)
        kwargs[f.name] = value
    return cls(**kwargs)
