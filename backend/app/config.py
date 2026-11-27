from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"
    analyst_enabled: bool = True
    analyst_provider: Literal["ollama", "workers_ai"] = "ollama"
    cloudflare_account_id: str | None = None
    cloudflare_ai_token: SecretStr | None = None
    workers_ai_model: str = "@cf/zai-org/glm-4.7-flash"

    @model_validator(mode="after")
    def validate_hosted_analyst(self):
        if self.analyst_enabled and self.analyst_provider == "workers_ai":
            if not self.cloudflare_account_id or not self.cloudflare_ai_token:
                raise ValueError("Workers AI requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_AI_TOKEN.")
        return self


settings = Settings()
