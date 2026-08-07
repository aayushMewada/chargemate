from flask.testing import FlaskClient
from sqlalchemy import select

from chargemate.extensions import db
from chargemate.models.user import User


def registration_payload() -> dict[str, str]:
    """Build credentials for protected-route tests."""
    return {
        "email": "protected@example.com",
        "username": "protected_user",
        "password": "a-long-test-password",
        "full_name": "Protected User",
    }


def login_and_get_access_token(client: FlaskClient) -> str:
    """Register, log in, and return the issued access token."""
    payload = registration_payload()
    client.post("/auth/register", json=payload)
    response = client.post(
        "/auth/login",
        json={
            "identifier": payload["email"],
            "password": payload["password"],
        },
    )
    return response.get_json()["access_token"]


def bearer_header(access_token: str) -> dict[str, str]:
    """Build an HTTP bearer-token header."""
    return {"Authorization": f"Bearer {access_token}"}


def test_me_rejects_missing_malformed_and_tampered_tokens(
    client: FlaskClient,
) -> None:
    access_token = login_and_get_access_token(client)

    missing = client.get("/auth/me")
    malformed = client.get(
        "/auth/me",
        headers={"Authorization": "Basic credentials"},
    )
    tampered = client.get(
        "/auth/me",
        headers=bearer_header(f"{access_token}tampered"),
    )

    assert missing.status_code == 401
    assert malformed.status_code == 401
    assert tampered.status_code == 401
    assert missing.get_json() == malformed.get_json() == tampered.get_json()


def test_me_returns_authenticated_user(client: FlaskClient) -> None:
    access_token = login_and_get_access_token(client)

    response = client.get("/auth/me", headers=bearer_header(access_token))

    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == "protected@example.com"
    assert "password_hash" not in response.get_json()["user"]


def test_me_rejects_user_deactivated_after_token_was_issued(
    client: FlaskClient,
) -> None:
    access_token = login_and_get_access_token(client)

    with client.application.app_context():
        user = db.session.scalar(
            select(User).where(User.email == "protected@example.com")
        )
        assert user is not None
        user.is_active = False
        db.session.commit()

    response = client.get("/auth/me", headers=bearer_header(access_token))
    assert response.status_code == 401


def test_logout_revokes_current_refresh_session(client: FlaskClient) -> None:
    access_token = login_and_get_access_token(client)
    refresh_cookie = client.get_cookie("refresh_token", path="/auth")
    assert refresh_cookie is not None

    logout_response = client.post(
        "/auth/logout",
        headers=bearer_header(access_token),
    )

    assert logout_response.status_code == 204
    assert client.get_cookie("refresh_token", path="/auth") is None

    client.set_cookie(
        "refresh_token",
        refresh_cookie.value,
        path="/auth",
    )
    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 401


def test_logout_all_revokes_every_refresh_session(client: FlaskClient) -> None:
    first_access_token = login_and_get_access_token(client)
    first_cookie = client.get_cookie("refresh_token", path="/auth")
    assert first_cookie is not None

    payload = registration_payload()
    second_login = client.post(
        "/auth/login",
        json={
            "identifier": payload["username"],
            "password": payload["password"],
        },
    )
    second_access_token = second_login.get_json()["access_token"]
    second_cookie = client.get_cookie("refresh_token", path="/auth")
    assert second_cookie is not None

    logout_response = client.post(
        "/auth/logout-all",
        headers=bearer_header(second_access_token),
    )
    assert logout_response.status_code == 204

    for cookie in (first_cookie, second_cookie):
        client.set_cookie("refresh_token", cookie.value, path="/auth")
        assert client.post("/auth/refresh").status_code == 401

    assert first_access_token != second_access_token
