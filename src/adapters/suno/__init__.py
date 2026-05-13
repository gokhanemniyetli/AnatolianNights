"""
Suno adapter factory.
Reads SUNO_CLIENT env var (manual|browser) and returns the correct client.
"""

from src.adapters.suno.isuno_client import ISunoClient
from src.adapters.suno.manual_client import ManualSunoClient


def get_suno_client() -> ISunoClient:
    from src.config.settings import settings
    client_type = settings.suno.client.lower()
    if client_type == "manual":
        return ManualSunoClient()
    if client_type == "browser":
        from src.adapters.suno.browser_client import BrowserSunoClient
        return BrowserSunoClient()
    raise ValueError(f"Unknown SUNO_CLIENT value: {client_type!r}")
