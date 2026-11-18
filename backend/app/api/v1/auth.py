from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.metrics import record_login_failure
from app.core.rate_limit import check_rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])

# Pre-computed bcrypt hash for constant-time comparison against nonexistent users
_DUMMY_HASH = "$2b$12$e80MvQcO4GZ37K50.dG3he9gI1xM9qPZZ3O7Y5hQnC4R7Vd8yWq2e"


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    data: UserCreate,
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(
        key=f"register:{client_ip}",
        max_requests=10,
        window_seconds=60,
        detail="Too many registration attempts. Please try again later.",
    )

    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if len(data.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password cannot exceed 72 bytes")

    existing = db.scalar(select(User).where(User.email == data.email))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=data.email, password_hash=hash_password(data.password), role="student")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(
        key=f"login:{client_ip}",
        max_requests=10,
        window_seconds=60,
        detail="Too many login attempts. Please try again later.",
    )

    if len(form.password.encode("utf-8")) > 72:
        record_login_failure()
        raise HTTPException(status_code=401, detail="Wrong email or password")

    user = db.scalar(select(User).where(User.email == form.username))
    if not user:
        # Constant-time mitigation to prevent user enumeration via timing attack
        verify_password(form.password, _DUMMY_HASH)
        record_login_failure()
        raise HTTPException(status_code=401, detail="Wrong email or password")

    if not verify_password(form.password, user.password_hash):
        record_login_failure()
        raise HTTPException(status_code=401, detail="Wrong email or password")

    return Token(access_token=create_access_token(user.id, user.role))
