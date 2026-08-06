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
