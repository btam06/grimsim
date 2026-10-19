# Grimsim

A Warhammer 40,000 army builder, combat calculator and game tracker.

**Rules edition:** Grimsim is intended for **Warhammer 40,000 11th edition, as of the
10/14/2026 update**. Its rules (combat resolution, stratagem timings, secondary
missions, etc.) follow that edition and may not match earlier or later ones.

## Features

- **Lists:** build army lists from datasheets, detachments and units, each owned by a
  user.
- **Calculator:** resolve one unit attacking another, with weapon, datasheet, faction
  and stratagem rules applied.
- **Games:** track two-player games through battle rounds, turns and phases, with CP,
  stratagems, primary and secondary missions, and VP. Several games can run at once.

## Running

Copy `.env.example` to `.env` and set a password, then:

```
docker compose up --build -d
```

The app is served at http://localhost:8080. Data is kept in the `pgdata` Docker
volume, so rebuilding keeps it. `docker compose down -v` deletes the volume and
everything in it.

On startup the backend creates any missing tables and seeds reference data
(factions, datasheets, abilities, core stratagems, ...). Seeding only adds what's
missing, so it's safe to run against an existing database.

## Development

Backend tests use an in-memory SQLite database:

```
cd backend
pip install -r requirements-dev.txt
pytest
```

Frontend (Vite + React), with `/api` proxied to a backend on port 8000:

```
cd frontend
npm install
npm run dev
```
