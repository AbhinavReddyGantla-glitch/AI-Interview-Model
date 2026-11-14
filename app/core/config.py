from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    APP_NAME: str = Field(default="AI Interview Evaluation Platform")
    APP_ENV: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    API_V1_STR: str = Field(default="/api/v1")
    
    # Database Configuration
    DATABASE_URL: str = Field(default="postgresql://postgres:password@localhost:5432/aidatabase")
    
    # Logging Configuration
    LOG_LEVEL: str = Field(default="INFO")

    # API Keys & Third-party APIs
    GEMINI_API_KEY: str = Field(default="")
    OPENAI_API_KEY: str = Field(default="")
    DEEPGRAM_API_KEY: str = Field(default="")
    DEEPGRAM_MODEL: str = Field(default="nova-2")
    DEEPGRAM_LANGUAGE: str = Field(default="en")
    AZURE_SPEECH_KEY: str = Field(default="")
    AZURE_SPEECH_REGION: str = Field(default="eastus")

    # Speech-to-Text Layered Pipeline Config
    STT_ENGINE: str = Field(default="whisper", description="whisper, openai, deepgram, or azure")
    WHISPER_MODEL: str = Field(default="base", description="base, small, medium.en, distil-large-v3, large-v3")
    WHISPER_DEVICE: str = Field(default="auto", description="auto, cpu, cuda")
    WHISPER_COMPUTE_TYPE: str = Field(default="default", description="default, int8, float16")
    WHISPER_BEAM_SIZE: int = Field(default=5)
    ENABLE_LLM_TRANSCRIPT_CORRECTION: bool = Field(default=False)
    STT_SIMILARITY_THRESHOLD: float = Field(default=0.80)
    STT_CONFIDENCE_THRESHOLD: float = Field(default=0.75)
    STT_VOCAB_PATH: str = Field(default="")

    # External Webhook URL (improvement / coaching team)
    EXTERNAL_EVALUATION_URL: str = Field(default="http://localhost:8000/api/v1/evaluation")
    EXTERNAL_WEBHOOK_SECRET: str = Field(default="")

    # SaaS API Authentication
    API_KEY: str = Field(default="", description="Set to require X-API-Key header on protected endpoints")

    # Public URL for interview links sent to candidates
    PUBLIC_BASE_URL: str = Field(default="http://localhost:8000")

    # Resume Processing Configuration
    MAX_RESUME_SIZE_MB: int = Field(default=5)
    RESUME_UPLOAD_DIR: str = Field(default="uploads/resumes")
    ENABLE_LLM_RESUME_PARSER: bool = Field(default=False)

settings = Settings()
