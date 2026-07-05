from __future__ import annotations
"""
Symmetric encryption for data at rest (Instagram session cookies).

Not a defense against full-host compromise -- protects against DB-only leaks
(backups, dumps, read replicas). ACCOUNT_ENCRYPTION_KEY must be a valid
Fernet key (44-char urlsafe-base64 string); generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet

from app.core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if not settings.ACCOUNT_ENCRYPTION_KEY:
        raise RuntimeError("ACCOUNT_ENCRYPTION_KEY is not configured")
    return Fernet(settings.ACCOUNT_ENCRYPTION_KEY.encode())


def encrypt_json(data: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict[str, Any]:
    return json.loads(_fernet().decrypt(token.encode()).decode())
