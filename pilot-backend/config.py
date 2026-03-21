from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Groq
    groq_api_key: str = "MISSING_KEY"

    # Groq models
    planner_model: str = "llama-3.3-70b-versatile"
    actor_model: str = "llama-3.3-70b-versatile"
    verifier_model: str = "llama-3.1-8b-instant"
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Ollama backup (remote via ngrok or any URL)
    ollama_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Task behaviour
    max_retries: int = 3
    max_back_presses: int = 5
    max_actions_per_step: int = 20


settings = Settings()
