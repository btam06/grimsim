from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    # Where games' autosaves go (see app/engine/saves.py).
    saves_dir: str = "saves"
    # Where the ML runs' diagnose files are (ml/diagnose.py's --out), for
    # the ML page (see app/routers/ml.py).
    ml_data_dir: str = "ml/data"
    # How long a game no request uses stays in memory, in minutes (see
    # app/engine/store.py).
    idle_minutes: float = 10

    class Config:
        env_file = ".env"
        # (Run from the project's root, .env is docker-compose's: its other
        # settings aren't the backend's.)
        extra = "ignore"


settings = Settings()
