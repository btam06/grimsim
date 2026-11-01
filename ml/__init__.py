import os
import sys

# Machine learning on the game engine (see README.md): the backend's `app`
# package is imported from ../backend, and games are played from saves - no
# database (app.config wants a URL all the same).
BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
