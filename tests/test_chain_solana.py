from app.chain import _is_solana_pubkey


def test_is_solana_pubkey_basic() -> None:
    # System Program ID (valid base58, 32 bytes)
    assert _is_solana_pubkey("11111111111111111111111111111111")
    assert not _is_solana_pubkey("")
    assert not _is_solana_pubkey("0x" + "0" * 40)
    assert not _is_solana_pubkey("not-a-solana-address")

