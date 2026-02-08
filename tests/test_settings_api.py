import importlib

from fastapi.testclient import TestClient


def test_settings_api_masks_and_preserves_password(monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    import app.crypto_store as crypto_store
    import app.settings as settings_mod

    monkeypatch.setattr(settings_mod, "DATA_DIR", data_dir)
    monkeypatch.setattr(settings_mod, "SETTINGS_OVERRIDE_PATH", data_dir / "app_settings.json")
    monkeypatch.setattr(crypto_store, "DATA_DIR", data_dir)
    monkeypatch.setattr(crypto_store, "KEY_PATH", data_dir / "secret.key")

    import app.main as main_mod

    importlib.reload(main_mod)
    client = TestClient(main_mod.app)

    r = client.post(
        "/api/v2/settings",
        json={
            "email_enabled": True,
            "mail_from": "from@example.com",
            "mail_to": ["a@example.com", "b@example.com"],
            "timezone": "Asia/Shanghai",
            "daily_job_time": "09:05",
            "notify_cooldown_minutes": 360,
            "crypto_slip_pct": 1.0,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user",
            "smtp_password": "secret-pass",
            "smtp_use_starttls": True,
        },
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("ok") is True

    override = payload.get("override") or {}
    assert "smtp_password_enc" not in override
    assert "smtp_password" not in override
    assert override.get("smtp_password_set") is True

    effective = payload.get("effective") or {}
    assert effective.get("smtp_password") == "***"

    # Send empty password: should NOT clear stored password.
    r2 = client.post("/api/v2/settings", json={"smtp_password": ""})
    assert r2.status_code == 200
    payload2 = r2.json()
    assert (payload2.get("override") or {}).get("smtp_password_set") is True

    # Ensure encrypted password still exists and decrypts.
    ov = settings_mod.load_settings_override()
    assert ov is not None
    assert ov.smtp_password_enc
    assert crypto_store.decrypt_str(ov.smtp_password_enc) == "secret-pass"

