from pathlib import Path

# Local game data that isn't committed (it's Games Workshop's): datasheets and
# mission cards, as JSON - see app/data/README.md. Seeds read from here at
# startup and skip anything that's missing.
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def data_dir() -> Path:
    # Read at call time (rather than imported as a value), so tests can point
    # DATA_DIR somewhere else.
    return DATA_DIR
