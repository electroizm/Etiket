from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str           # service_role — scraper + admin işlemleri
    supabase_anon_key: str      # anon — frontend okuma
    secret_key: str             # JWT imzalama
    trial_days: int = 14
    iyzico_api_key: str = ""
    iyzico_secret_key: str = ""

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
