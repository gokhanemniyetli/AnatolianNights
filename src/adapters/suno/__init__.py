"""
Suno adapter factory.
Reads SUNO_CLIENT env var (manual|browser) and returns the correct client.
"""

import os

from src.adapters.suno.isuno_client import ISunoClient
from src.adapters.suno.manual_client import ManualSunoClient


def get_suno_client() -> ISunoClient:
    client_type = os.getenv("SUNO_CLIENT", "manual").lower()
    if client_type == "manual":
        return ManualSunoClient()
    if client_type == "browser":
        # Phase 2 — browser automation not yet implemented
        raise NotImplementedError("BrowserSunoClient is Phase 2. Set SUNO_CLIENT=manual.")
    raise ValueError(f"Unknown SUNO_CLIENT value: {client_type!r}")
