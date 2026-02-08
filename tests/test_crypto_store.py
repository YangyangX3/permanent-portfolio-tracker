from app.crypto_store import decrypt_str, encrypt_str


def test_encrypt_decrypt_roundtrip() -> None:
    token = encrypt_str("secret")
    assert token and token != "secret"
    assert decrypt_str(token) == "secret"

