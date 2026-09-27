import os
import tempfile
from datetime import timedelta

_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ADMIN_EMAILS"] = "admin@example.com"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.deps import today  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client, email, name="Member", **extra):
    r = client.post("/auth/register", json={"name": name, "email": email, "password": "password123", **extra})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r


@pytest.fixture
def admin(client):
    return register(client, "admin@example.com", "Admin")[0]


@pytest.fixture
def challenge(client, admin):
    t = today()
    r = client.post(
        "/challenges",
        headers=admin,
        json={
            "name": "100 Days of Python",
            "start_date": str(t - timedelta(days=9)),
            "end_date": str(t + timedelta(days=90)),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()
