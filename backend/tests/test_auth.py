from __future__ import annotations


def test_bootstrap_creates_owner_and_signs_in(app_client):
    r = app_client.post("/api/auth/status")
    r = app_client.get("/api/auth/status")
    assert r.json() == {"owner_exists": False}

    r = app_client.post("/api/auth/bootstrap", json={"username": "owner", "password": "testpass123"})
    assert r.status_code == 200
    r = app_client.get("/api/auth/me")
    assert r.status_code == 200 and r.json()["username"] == "owner"


def test_bootstrap_refused_once_an_owner_exists(app_client):
    app_client.post("/api/auth/bootstrap", json={"username": "owner", "password": "testpass123"})
    r = app_client.post("/api/auth/bootstrap", json={"username": "someone-else", "password": "testpass123"})
    assert r.status_code == 409


def test_unauthorized_user_denied_settings_access(app_client):
    for path in ["/api/settings/gemini", "/api/settings/linkedin", "/api/settings/brand", "/api/channels"]:
        r = app_client.get(path)
        assert r.status_code == 401, path


def test_login_with_wrong_password_rejected(app_client):
    app_client.post("/api/auth/bootstrap", json={"username": "owner", "password": "testpass123"})
    app_client.post("/api/auth/logout")
    r = app_client.post("/api/auth/login", json={"username": "owner", "password": "wrong-password"})
    assert r.status_code == 401


def test_logout_clears_session(authed_client):
    assert authed_client.get("/api/auth/me").status_code == 200
    authed_client.post("/api/auth/logout")
    assert authed_client.get("/api/auth/me").status_code == 401
