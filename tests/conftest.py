import os, tempfile, pytest
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")  # до импорта app

from fastapi.testclient import TestClient
from app.main import app, seed
from app.models import Base, engine


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed()
    yield


@pytest.fixture
def c():
    with TestClient(app) as cl:
        yield cl


def _auth(c, email, pw):
    r = c.post("/api/login", json={"email": email, "password": pw})
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture
def client_h(c):
    return _auth(c, "client@rent.local", "client123")


@pytest.fixture
def manager_h(c):
    return _auth(c, "manager@rent.local", "manager123")


@pytest.fixture
def admin_h(c):
    return _auth(c, "admin@rent.local", "admin123")
