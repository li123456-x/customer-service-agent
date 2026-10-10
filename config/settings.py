from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    dashscope_api_key: str
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str
    milvus_uri: str
    milvus_db_name: str = "customer_service_kb"
    milvus_collection_name: str = "docs"
    rag_top_k: int = Field(default=5, ge=1, le=100)
    rag_min_relevance_score: float = Field(default=0.55, ge=-1, le=1)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
