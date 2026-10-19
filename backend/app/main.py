import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .models import User
from .schemas import LoginRequest, LoginResponse, UserCreate, UserResponse, UserUpdate
from .security import create_access_token, decode_access_token, hash_password, verify_password

bearer_scheme = HTTPBearer(auto_error=False)


def seed_users() -> None:
    with SessionLocal() as db:
        accounts = [
            {
                "email": os.getenv("ADMIN_EMAIL", "ashish@authmantra.com").lower(),
                "legacy_email": "admin@example.com",
                "legacy_display_name": "Alex Morgan",
                "password": os.getenv("ADMIN_PASSWORD", "AdminPass123!"),
                "role": "admin",
                "display_name": "Ashish",
            },
            {
                "email": os.getenv("TEST_USER_EMAIL", "poc@authmantra.com").lower(),
                "legacy_email": "test@example.com",
                "legacy_display_name": "Taylor Reed",
                "password": os.getenv("TEST_USER_PASSWORD", "TestPass123!"),
                "role": "user",
                "display_name": "POC User",
            },
        ]
        for account in accounts:
            existing = db.scalar(select(User).where(User.email == account["email"]))
            legacy_user = db.scalar(select(User).where(User.email == account["legacy_email"]))
            is_legacy_seed = (
                legacy_user is not None
                and legacy_user.role == account["role"]
                and legacy_user.display_name == account["legacy_display_name"]
            )
            if existing is None and is_legacy_seed:
                legacy_user.email = account["email"]
                legacy_user.display_name = account["display_name"]
            elif (
                existing is not None
                and is_legacy_seed
                and legacy_user.id != existing.id
            ):
                db.delete(legacy_user)
            elif existing is None:
                db.add(
                    User(
                        email=account["email"],
                        password_hash=hash_password(account["password"]),
                        role=account["role"],
                        display_name=account["display_name"],
                    )
                )
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_users()
    yield


app = FastAPI(title="AuthMantra API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid authentication is required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = int(claims["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
        )
    token = create_access_token(user.id, user.email, user.role)
    return LoginResponse(
        access_token=token,
        user=user_response(user),
    )


@app.get("/api/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    users = db.scalars(select(User).order_by(User.id)).all()
    return [user_response(user) for user in users]


@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        display_name=payload.display_name.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_response(user)


@app.patch("/api/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes and changes["email"] is not None:
        email = str(changes["email"]).lower()
        duplicate = db.scalar(select(User).where(User.email == email, User.id != user.id))
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")
        user.email = email
    if "password" in changes and changes["password"] is not None:
        user.password_hash = hash_password(changes["password"])
    if "display_name" in changes and changes["display_name"] is not None:
        user.display_name = changes["display_name"].strip()
    if changes.get("role") is not None and user.role == "admin" and changes["role"] != "admin":
        admin_count = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The last administrator cannot be demoted")
        user.role = changes["role"]
    elif changes.get("role") is not None:
        user.role = changes["role"]
    db.commit()
    db.refresh(user)
    return user_response(user)


@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot delete your own account")
    if user.role == "admin":
        admin_count = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The last administrator cannot be deleted")
    db.delete(user)
    db.commit()
