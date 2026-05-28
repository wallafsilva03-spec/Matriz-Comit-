from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_key: str = Field(..., env="SUPABASE_KEY")
    database_url: str = Field(..., env="DATABASE_URL")

    # Pastas
    input_folder: Path = Field(default=Path("data/input"), env="INPUT_FOLDER")
    processed_folder: Path = Field(default=Path("data/processed"), env="PROCESSED_FOLDER")
    error_folder: Path = Field(default=Path("data/error"), env="ERROR_FOLDER")
    log_folder: Path = Field(default=Path("logs"), env="LOG_FOLDER")

    # Comportamento
    watch_interval: int = Field(default=10, env="WATCH_INTERVAL")
    batch_size: int = Field(default=500, env="BATCH_SIZE")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def ensure_folders(self) -> None:
        for folder in [self.input_folder, self.processed_folder, self.error_folder, self.log_folder]:
            Path(folder).mkdir(parents=True, exist_ok=True)


settings = Settings()
