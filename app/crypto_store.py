from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KEY_PATH = DATA_DIR / "secret.key"


def _load_or_create_key() -> bytes:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_PATH.exists():
        key = KEY_PATH.read_bytes().strip()
        if key:
            return key
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt_str(plain: str) -> str:
    if plain is None:
        return ""
    s = str(plain)
    if not s:
        return ""
    token = _fernet().encrypt(s.encode("utf-8"))
    return token.decode("ascii")


def decrypt_str(token: str) -> str | None:
    t = (token or "").strip()
    if not t:
        return None
    try:
        raw = _fernet().decrypt(t.encode("ascii"))
        return raw.decode("utf-8")
    except (InvalidToken, ValueError):
        return None

