from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    # Where games' autosaves go (see app/engine/saves.py).
    saves_dir: str = "saves"

    class Config:
        env_file = ".env"


settings = Settings()
