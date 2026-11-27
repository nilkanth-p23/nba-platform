from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"
    analyst_enabled: bool = True


settings = Settings()
