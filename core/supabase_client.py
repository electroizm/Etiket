from supabase import create_client, Client
from core.config import get_settings

_client: Client | None = None


def get_supabase() -> Client:
    """Singleton Supabase bağlantısı (service_role — tam yetki)"""
    global _client
    if _client is None:
        s = get_settings()
        _client = create_client(s.supabase_url, s.supabase_key)
    return _client
