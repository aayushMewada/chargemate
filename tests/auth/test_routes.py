from flask.testing import FlaskClient


def registration_payload(**overrides: str | None) -> dict[str, str | None]:
    """Build a valid public registration request."""
    payload = {
        "email": "Driver@Example.com",
        "username": "driver_one",
        "password": "a-long-test-password",
        "full_name": "Test Driver",
        "phone": "+919876543210",
    }
    payload.update(overrides)
    return payload


def login_payload(
    identifier: str = "driver@example.com",
    password: str = "a-long-test-password",
) -> dict[str, str]:
    """Build a valid public login request."""
    return {"identifier": identifier, "password": password}


def test_register_endpoint_creates_user(client: FlaskClient) -> None:
    response = client.post("/auth/register", json=registration_payload())

    assert response.status_code == 201
    body = response.get_json()
    assert body["user"]["email"] == "driver@example.com"
    assert body["user"]["username"] == "driver_one"
    assert body["user"]["role"] == "user"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_register_endpoint_rejects_invalid_json(client: FlaskClient) -> None:
    response = client.post(
        "/auth/register",
        data='{"email":',
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_json"


def test_register_endpoint_rejects_invalid_fields(client: FlaskClient) -> None:
    payload = registration_payload(password="Le@k7")
    payload["role"] = "system_admin"

    response = client.post("/auth/register", json=payload)

    assert response.status_code == 422
    body = response.get_json()
    assert body["error"]["code"] == "validation_error"
    assert {detail["field"] for detail in body["error"]["details"]} == {
        "password",
        "role",
    }
    assert "Le@k7" not in response.get_data(as_text=True)


def test_register_endpoint_rejects_duplicate_identity(
    client: FlaskClient,
) -> None:
    first_response = client.post("/auth/register", json=registration_payload())
    duplicate_response = client.post(
        "/auth/register",
        json=registration_payload(username="another_driver", phone=None),
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.get_json()["error"]["code"] == (
        "registration_conflict"
    )


def test_login_endpoint_accepts_email_or_username(client: FlaskClient) -> None:
    client.post("/auth/register", json=registration_payload())

    email_response = client.post("/auth/login", json=login_payload())
    username_response = client.post(
        "/auth/login",
        json=login_payload(identifier="driver_one"),
    )

    assert email_response.status_code == 200
    assert username_response.status_code == 200
    assert email_response.get_json()["user"]["email"] == "driver@example.com"
    assert "password_hash" not in email_response.get_json()["user"]


def test_login_endpoint_returns_same_error_for_invalid_identity(
    client: FlaskClient,
) -> None:
    client.post("/auth/register", json=registration_payload())

    wrong_password = client.post(
        "/auth/login",
        json=login_payload(password="incorrect-password"),
    )
    missing_user = client.post(
        "/auth/login",
        json=login_payload(identifier="missing@example.com"),
    )

    assert wrong_password.status_code == 401
    assert missing_user.status_code == 401
    assert wrong_password.get_json() == missing_user.get_json()
    assert wrong_password.get_json()["error"]["code"] == "invalid_credentials"


def test_login_endpoint_locks_account_after_five_failures(
    client: FlaskClient,
) -> None:
    client.post("/auth/register", json=registration_payload())

    failed_responses = [
        client.post(
            "/auth/login",
            json=login_payload(password="incorrect-password"),
        )
        for _ in range(5)
    ]
    correct_password_while_locked = client.post(
        "/auth/login",
        json=login_payload(),
    )

    assert all(response.status_code == 401 for response in failed_responses)
    assert correct_password_while_locked.status_code == 401
    assert correct_password_while_locked.get_json()["error"]["code"] == (
        "invalid_credentials"
    )
