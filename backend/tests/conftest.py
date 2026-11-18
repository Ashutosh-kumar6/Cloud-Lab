import os
import shutil
from typing import Generator

# Ensure testing environment is active before anything else is imported
os.environ["ENVIRONMENT"] = "testing"
os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-at-least-32-characters-long")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
settings.environment = "testing"

from app.core.rate_limit import reset_rate_limits
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services import storage

# In-memory SQLite with StaticPool for total test isolation
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False)


@pytest.fixture(autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=test_engine)
    reset_rate_limits()
    yield
    Base.metadata.drop_all(bind=test_engine)
    reset_rate_limits()
    if storage.STORAGE_DIR.exists():
        shutil.rmtree(storage.STORAGE_DIR, ignore_errors=True)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def student_user(db: Session) -> User:
    user = User(
        email="student@cloudlab.edu",
        password_hash=hash_password("student123"),
        role="student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_student_user(db: Session) -> User:
    user = User(
        email="other_student@cloudlab.edu",
        password_hash=hash_password("student123"),
        role="student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def teacher_user(db: Session) -> User:
    user = User(
        email="teacher@cloudlab.edu",
        password_hash=hash_password("teacher123"),
        role="teacher",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db: Session) -> User:
    user = User(
        email="admin@cloudlab.edu",
        password_hash=hash_password("admin123"),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def student_token(student_user: User) -> str:
    return create_access_token(student_user.id, student_user.role)


@pytest.fixture
def other_student_token(other_student_user: User) -> str:
    return create_access_token(other_student_user.id, other_student_user.role)


@pytest.fixture
def teacher_token(teacher_user: User) -> str:
    return create_access_token(teacher_user.id, teacher_user.role)


@pytest.fixture
def admin_token(admin_user: User) -> str:
    return create_access_token(admin_user.id, admin_user.role)


@pytest.fixture
def auth_headers():
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _headers
