"""Authentication, RBAC and session endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.constants import UserRole


def test_login_returns_tokens_and_profile(client: TestClient, seeded_users) -> None:
    response = client.post(
        "/api/login",
        json={"email": seeded_users["recruiter"]["email"], "password": seeded_users["recruiter"]["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"].lower() == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0
    assert body["user"]["role"] == UserRole.RECRUITER.value
    assert "resume:upload" in body["user"]["permissions"]
    assert "hashed_password" not in body["user"]


def test_login_is_case_insensitive_on_email(client: TestClient, seeded_users) -> None:
    response = client.post(
        "/api/login",
        json={
            "email": seeded_users["manager"]["email"].upper(),
            "password": seeded_users["manager"]["password"],
        },
    )
    assert response.status_code == 200


def test_login_with_wrong_password_is_rejected(client: TestClient, seeded_users) -> None:
    response = client.post(
        "/api/login", json={"email": seeded_users["admin"]["email"], "password": "not-the-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"


def test_login_with_unknown_email_is_rejected(client: TestClient) -> None:
    response = client.post("/api/login", json={"email": "ghost@example.com", "password": "whatever"})
    assert response.status_code == 401


def test_protected_endpoint_requires_token(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_me_returns_current_user(client: TestClient, admin_headers) -> None:
    response = client.get("/api/me", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == UserRole.HR_ADMIN.value
    assert body["role_label"]


def test_refresh_rotates_tokens(client: TestClient, seeded_users) -> None:
    login = client.post(
        "/api/login",
        json={"email": seeded_users["recruiter"]["email"], "password": seeded_users["recruiter"]["password"]},
    ).json()

    refreshed = client.post("/api/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["access_token"] != login["access_token"]

    headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
    assert client.get("/api/me", headers=headers).status_code == 200


def test_access_token_cannot_be_used_to_refresh(client: TestClient, seeded_users) -> None:
    login = client.post(
        "/api/login",
        json={"email": seeded_users["recruiter"]["email"], "password": seeded_users["recruiter"]["password"]},
    ).json()
    assert client.post("/api/refresh", json={"refresh_token": login["access_token"]}).status_code == 401


def test_logout_revokes_the_session(client: TestClient, seeded_users) -> None:
    login = client.post(
        "/api/login",
        json={"email": seeded_users["manager"]["email"], "password": seeded_users["manager"]["password"]},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.post("/api/logout", json={"all_sessions": False}, headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401


def test_forgot_and_reset_password_flow(client: TestClient) -> None:
    from app.db.session import SessionLocal
    from app.services.auth import create_user

    email = "reset.flow@example.com"
    session = SessionLocal()
    try:
        create_user(
            session,
            email=email,
            full_name="Reset Flow",
            password="InitialPass#1",
            role=UserRole.RECRUITER,
        )
        session.commit()
    finally:
        session.close()

    forgot = client.post("/api/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    token = forgot.json()["reset_token"]
    assert token, "the test environment exposes the token instead of sending mail"

    reset = client.post("/api/reset-password", json={"token": token, "new_password": "BrandNewPass#2"})
    assert reset.status_code == 200

    assert client.post("/api/login", json={"email": email, "password": "InitialPass#1"}).status_code == 401
    assert client.post("/api/login", json={"email": email, "password": "BrandNewPass#2"}).status_code == 200

    # Reset tokens are single use.
    assert client.post("/api/reset-password", json={"token": token, "new_password": "Another#3"}).status_code in {
        400,
        401,
        422,
    }


def test_forgot_password_does_not_leak_account_existence(client: TestClient) -> None:
    response = client.post("/api/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    assert response.json()["reset_token"] is None


def test_change_password(client: TestClient) -> None:
    from app.db.session import SessionLocal
    from app.services.auth import create_user

    email = "change.pass@example.com"
    session = SessionLocal()
    try:
        create_user(
            session, email=email, full_name="Change Pass", password="FirstPass#1", role=UserRole.RECRUITER
        )
        session.commit()
    finally:
        session.close()

    login = client.post("/api/login", json={"email": email, "password": "FirstPass#1"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    weak = client.post(
        "/api/change-password",
        json={"current_password": "FirstPass#1", "new_password": "short"},
        headers=headers,
    )
    assert weak.status_code in {400, 422}

    changed = client.post(
        "/api/change-password",
        json={"current_password": "FirstPass#1", "new_password": "SecondPass#2"},
        headers=headers,
    )
    assert changed.status_code == 200
    assert client.post("/api/login", json={"email": email, "password": "SecondPass#2"}).status_code == 200


def test_rbac_blocks_user_management_for_recruiters(client: TestClient, recruiter_headers) -> None:
    response = client.get("/api/users", headers=recruiter_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_admin_can_manage_users(client: TestClient, admin_headers) -> None:
    listed = client.get("/api/users", headers=admin_headers)
    assert listed.status_code == 200
    assert any(user["role"] == UserRole.HR_ADMIN.value for user in listed.json())

    created = client.post(
        "/api/users",
        json={
            "email": "new.recruiter@example.com",
            "full_name": "New Recruiter",
            "password": "NewRecruit#1",
            "role": UserRole.RECRUITER.value,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    updated = client.put(f"/api/users/{user_id}", json={"is_active": False}, headers=admin_headers)
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    assert (
        client.post(
            "/api/login", json={"email": "new.recruiter@example.com", "password": "NewRecruit#1"}
        ).status_code
        == 401
    )


def test_hiring_manager_cannot_upload_resumes(client: TestClient, manager_headers) -> None:
    response = client.post(
        "/api/upload",
        files=[("files", ("x.txt", b"John Doe\nPython", "text/plain"))],
        headers=manager_headers,
    )
    assert response.status_code == 403


def test_sessions_endpoint_lists_active_sessions(client: TestClient, admin_headers) -> None:
    response = client.get("/api/me/sessions", headers=admin_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_audit_log_records_logins(client: TestClient, admin_headers) -> None:
    response = client.get("/api/users/audit/logs", headers=admin_headers)
    assert response.status_code == 200
    actions = {item["action"] for item in response.json()["items"]}
    assert "login" in actions or "user_create" in actions
