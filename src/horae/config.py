from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HORAE_")

    radicale_url: str = "http://localhost:5232"
    radicale_username: str
    radicale_password: SecretStr
    default_calendar: str = "personal"
    default_duration_minutes: int = 60
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
