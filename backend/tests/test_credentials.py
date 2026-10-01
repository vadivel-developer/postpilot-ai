from __future__ import annotations

from app.security.secrets import decrypt, encrypt, mask


def test_encrypt_round_trip():
    secret = "AIzaSyFAKE-not-a-real-key-1234567890"
    enc = encrypt(secret)
    assert enc != secret
    assert decrypt(enc) == secret


def test_mask_never_reveals_more_than_the_tail():
    assert mask("sk-verylongsecretkeyabc123") == "•" * 22 + "c123"
    assert "sk-verylongsecretkeyabc123"[:-4] not in mask("sk-verylongsecretkeyabc123")


def test_gemini_key_never_returned_by_status(db_session):
    from app.services import credentials as cred

    cred.set_gemini_api_key(db_session, "sk-test-real-secret-value-zzz")
    status = cred.gemini_status(db_session)
    assert status.configured is True
    assert status.source == "ui"
    assert "sk-test-real-secret-value-zzz" not in (status.masked or "")


def test_ui_credential_overrides_env_and_removal_restores_env(db_session, monkeypatch):
    from app.services import credentials as cred

    monkeypatch.setenv("GEMINI_API_KEY", "env-provided-key")
    status = cred.gemini_status(db_session)
    assert status.configured is True and status.source == "env"
    assert cred.get_gemini_api_key(db_session) == "env-provided-key"

    cred.set_gemini_api_key(db_session, "ui-provided-key")
    assert cred.get_gemini_api_key(db_session) == "ui-provided-key"
    assert cred.gemini_status(db_session).source == "ui"

    cred.remove_gemini_api_key(db_session)
    assert cred.get_gemini_api_key(db_session) == "env-provided-key"
    assert cred.gemini_status(db_session).source == "env"


def test_linkedin_credentials_encrypted_and_removable(db_session):
    from app.services import credentials as cred

    cred.set_linkedin_app_credentials(db_session, "client-id-123", "super-secret-value")
    client_id, secret = cred.get_linkedin_app_credentials(db_session)
    assert client_id == "client-id-123" and secret == "super-secret-value"

    from app.models.db import LinkedInCredential

    row = db_session.get(LinkedInCredential, 1)
    assert "super-secret-value" not in (row.encrypted_client_secret or "")

    cred.remove_linkedin_app_credentials(db_session)
    client_id2, secret2 = cred.get_linkedin_app_credentials(db_session)
    assert client_id2 is None and secret2 is None


def test_settings_endpoints_never_return_secret_values(authed_client):
    authed_client.put("/api/settings/gemini", json={"api_key": "sk-real-secret-abcdefgh"})
    r = authed_client.get("/api/settings/gemini")
    body = r.json()
    assert "sk-real-secret-abcdefgh" not in str(body)
    assert body["configured"] is True

    authed_client.put("/api/settings/linkedin", json={"client_id": "abc", "client_secret": "super-secret-linkedin-value"})
    r2 = authed_client.get("/api/settings/linkedin")
    assert "super-secret-linkedin-value" not in str(r2.json())


def test_credential_replace_and_remove_via_api(authed_client):
    authed_client.put("/api/settings/gemini", json={"api_key": "first-key-value"})
    assert authed_client.get("/api/settings/gemini").json()["configured"] is True
    authed_client.put("/api/settings/gemini", json={"api_key": "second-key-value"})
    r = authed_client.delete("/api/settings/gemini")
    assert r.status_code == 200
    assert authed_client.get("/api/settings/gemini").json()["configured"] is False
