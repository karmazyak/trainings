from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenRouter LLM
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-4.1-mini"
    llm_model_cheap: str = "openai/gpt-4.1-mini"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trainings"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # RAG
    rag_top_k: int = 10
    rag_use_reranking: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
