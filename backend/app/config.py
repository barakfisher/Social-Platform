from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "postgresql+psycopg://social_app:social_app_local@localhost:55473/social"
    migration_database_url: str | None = None
    redis_url: str = "redis://localhost:56373/0"
    embedding_api_key: SecretStr = SecretStr("")
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1, le=2000)
    embedding_revision: str = "1"
    embedding_batch_size: int = Field(default=16, ge=1, le=16)
    embedding_timeout: float = Field(default=20, ge=1, le=30)
    generation_api_key: SecretStr = SecretStr("")
    generation_base_url: str = "https://openrouter.ai/api/v1"
    generation_model: str = "openai/gpt-4.1"
    # Default source-check model; users may pick any model in generation_review_models.
    generation_review_model: str = "openai/gpt-5.6-terra"
    generation_review_models: list[str] = Field(
        default=["openai/gpt-5.6-terra", "openai/gpt-4.1"], min_length=1, max_length=5
    )
    generation_tokenizer: str = "o200k_base"
    generation_timeout: float = Field(default=40, ge=1, le=40)
    generation_retries: int = Field(default=1, ge=0, le=2)
    generation_max_output_tokens: int = Field(default=900, ge=100, le=2000)
    # Claim-level reviews repeat every claim and its quotes, and reasoning reviewers spend
    # part of this limit thinking; see docs/implementation.md.
    generation_review_max_output_tokens: int = Field(default=4000, ge=100, le=4000)
    generation_prompt_budget: int = Field(default=6000, ge=1000, le=16000)
    generation_context_budget: int = Field(default=2800, ge=100, le=6000)
    generation_retrieval_count: int = Field(default=5, ge=1, le=10)
    generation_max_distance: float = Field(default=0.65, ge=0, le=2)
    generation_max_request_usd: float = Field(default=0.31, gt=0, le=1)
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:53073",
        "http://127.0.0.1:53073",
    ]

    @model_validator(mode="after")
    def default_review_model_is_offered(self):
        if self.generation_review_model not in self.generation_review_models:
            raise ValueError("GENERATION_REVIEW_MODEL must be one of GENERATION_REVIEW_MODELS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
