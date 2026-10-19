import os

os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import create_access_token, hash_password


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=test_engine)
with TestSession() as db:
    db.add(
        User(
            email="admin@example.com",
            password_hash=hash_password("AdminPass123!"),
            role="admin",
            display_name="Alex Morgan",
        )
    )
    db.add(
        User(
            email="poc@authmantra.com",
            password_hash=hash_password("TestPass123!"),
            role="user",
            display_name="POC User",
        )
    )
    db.commit()


def override_get_db():
    with TestSession() as db:
        yield db


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_login_returns_role_and_token():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "AdminPass123!"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"
    assert response.json()["access_token"]


def test_login_rejects_invalid_password():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


def test_admin_can_list_users():
    token = create_access_token(1, "admin@example.com", "admin")
    response = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert {user["role"] for user in response.json()} == {"admin", "user"}


def test_poc_user_cannot_list_or_change_users():
    token = create_access_token(2, "poc@authmantra.com", "user")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.post(
        "/api/users",
        headers=headers,
        json={"email": "new@example.com", "password": "NewPass123!", "display_name": "New", "role": "user"},
    ).status_code == 403


def test_admin_can_create_update_and_delete_user():
    token = create_access_token(1, "admin@example.com", "admin")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/users",
        headers=headers,
        json={"email": "managed@example.com", "password": "ManagedPass123!", "display_name": "Managed User", "role": "user"},
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    updated = client.patch(
        f"/api/users/{user_id}",
        headers=headers,
        json={"display_name": "Updated User"},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Updated User"

    deleted = client.delete(f"/api/users/{user_id}", headers=headers)
    assert deleted.status_code == 204


def test_startup_seed_migrates_legacy_accounts_once(monkeypatch):
    seed_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=seed_engine)
    SeedSession = sessionmaker(bind=seed_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(main_module, "SessionLocal", SeedSession)
    monkeypatch.setenv("ADMIN_EMAIL", "ashish@authmantra.com")
    monkeypatch.setenv("TEST_USER_EMAIL", "poc@authmantra.com")
    with SeedSession() as db:
        db.add_all(
            [
                User(email="admin@example.com", password_hash=hash_password("AdminPass123!"), role="admin", display_name="Alex Morgan"),
                User(email="test@example.com", password_hash=hash_password("TestPass123!"), role="user", display_name="Taylor Reed"),
            ]
        )
        db.commit()

    main_module.seed_users()
    main_module.seed_users()

    with SeedSession() as db:
        emails = [user.email for user in db.query(User).all()]
    assert sorted(emails) == ["ashish@authmantra.com", "poc@authmantra.com"]
