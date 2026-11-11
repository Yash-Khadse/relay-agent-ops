from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RELAY_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/relay.db"
    checkpoint_url: str = "sqlite:///./data/checkpoints.db"
    provider: Literal["fixture", "ollama", "groq", "gemini"] = "fixture"
    model: str = ""
    api_key: str = ""
    ollama_url: str = "http://localhost:11434/v1"
    crew_enabled: bool = False
    crew_model: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]
    cookie_secure: bool = False
    demo_enabled: bool = True
    public_live_enabled: bool = False
    max_executions: int = Field(10, ge=1, le=1000)
    global_daily_executions: int = Field(100, ge=1)
    session_hours: int = Field(24, ge=1, le=168)
    approval_hours: int = Field(24, ge=1, le=168)
    max_run_seconds: int = Field(240, ge=5, le=600)
    lease_seconds: int = Field(300, ge=30)
    max_job_attempts: int = Field(3, ge=1, le=5)
    max_model_calls: int = Field(12, ge=1, le=50)
    max_input_tokens: int = Field(30000, ge=100)
    max_output_tokens: int = Field(12000, ge=100)
    model_timeout_seconds: int = Field(45, ge=1, le=120)
    fallback_provider: str = ""
    fallback_model: str = ""
    fallback_api_key: str = ""
    queue_mode: Literal["database", "sqs"] = "database"
    sqs_queue_url: str = ""
    data_dir: Path = Path("data")
    static_dir: str = ""

    @model_validator(mode="after")
    def validate_runtime(self):
        if self.lease_seconds <= self.max_run_seconds:
            raise ValueError("lease_seconds must exceed max_run_seconds")
        if self.queue_mode == "sqs" and (
            not self.sqs_queue_url or self.database_url.startswith("sqlite")
        ):
            raise ValueError("SQS requires a queue URL and persistent PostgreSQL")
        return self

    @property
    def configured(self) -> bool:
        return self.provider == "fixture" or bool(
            self.model and (self.provider == "ollama" or self.api_key)
        )
