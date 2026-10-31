import os
import base64
import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request as URLRequest, urlopen

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from jwt import PyJWKClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .models import User
from .schemas import LoginRequest, LoginResponse, UserCreate, UserResponse, UserUpdate
from .security import create_access_token, decode_access_token, hash_password, verify_password

bearer_scheme = HTTPBearer(auto_error=False)
OKTA_STATE_COOKIE = "okta_oauth_state"
OKTA_NONCE_COOKIE = "okta_oauth_nonce"
OKTA_VERIFIER_COOKIE = "okta_pkce_verifier"


def okta_configuration() -> tuple[str, str, str, str] | None:
    issuer = os.getenv("OKTA_ISSUER", "").rstrip("/")
    client_id = os.getenv("OKTA_CLIENT_ID", "")
    client_secret = os.getenv("OKTA_CLIENT_SECRET", "")
    redirect_uri = os.getenv("OKTA_REDIRECT_URI", "http://localhost:8000/api/auth/okta/callback")
    if not issuer or not client_id or not client_secret:
        return None
    return issuer, client_id, client_secret, redirect_uri


def okta_metadata(issuer: str) -> dict:
    request = URLRequest(f"{issuer}/.well-known/openid-configuration")
    with urlopen(request, timeout=10) as response:
        metadata = json.loads(response.read())
    if metadata.get("issuer", "").rstrip("/") != issuer:
        raise ValueError("Okta issuer did not match discovery metadata")
    return metadata


def clear_okta_cookies(response: RedirectResponse, secure: bool) -> None:
    for cookie_name in (OKTA_STATE_COOKIE, OKTA_NONCE_COOKIE, OKTA_VERIFIER_COOKIE):
        response.delete_cookie(cookie_name, path="/api/auth/okta/callback", secure=secure, httponly=True, samesite="lax")


def okta_error_redirect(secure: bool, reason: str = "okta_login_failed") -> RedirectResponse:
    response = RedirectResponse(
        f"{os.getenv('FRONTEND_ORIGIN', 'http://localhost:3000').rstrip('/')}/#auth_error={quote(reason)}"
    )
    clear_okta_cookies(response, secure)
    return response


def userinfo_error_reason(id_token_claims: dict, userinfo: dict) -> str | None:
    userinfo_sub = userinfo.get("sub")
    if not isinstance(userinfo_sub, str) or not secrets.compare_digest(id_token_claims["sub"], userinfo_sub):
        return "okta_subject_mismatch"
    email = userinfo.get("email")
    if not isinstance(email, str) or userinfo.get("email_verified") is not True:
        return "okta_email_unverified"
    return None


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


@app.get("/api/auth/okta/login")
def okta_login():
    configuration = okta_configuration()
    if configuration is None:
        frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")
        return RedirectResponse(f"{frontend_origin}/#auth_error=okta_not_configured")
    issuer, client_id, _, redirect_uri = configuration
    try:
        metadata = okta_metadata(issuer)
        authorization_endpoint = metadata["authorization_endpoint"]
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Okta discovery is unavailable") from None

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "response_mode": "query",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    response = RedirectResponse(f"{authorization_endpoint}?{query}")
    secure = redirect_uri.startswith("https://")
    for name, value in ((OKTA_STATE_COOKIE, state), (OKTA_NONCE_COOKIE, nonce), (OKTA_VERIFIER_COOKIE, verifier)):
        response.set_cookie(name, value, max_age=600, path="/api/auth/okta/callback", secure=secure, httponly=True, samesite="lax")
    return response


@app.get("/api/auth/okta/callback")
def okta_callback(request: Request, db: Session = Depends(get_db)):
    configuration = okta_configuration()
    if configuration is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Okta sign-in is not configured")
    issuer, client_id, client_secret, redirect_uri = configuration
    secure = redirect_uri.startswith("https://")
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if request.query_params.get("error"):
        return okta_error_redirect(secure, "okta_provider_error")
    if (
        not code
        or not state
        or not secrets.compare_digest(state, request.cookies.get(OKTA_STATE_COOKIE, ""))
        or not request.cookies.get(OKTA_NONCE_COOKIE)
        or not request.cookies.get(OKTA_VERIFIER_COOKIE)
    ):
        return okta_error_redirect(secure, "okta_state_invalid")

    try:
        metadata = okta_metadata(issuer)
        token_request = URLRequest(
            metadata["token_endpoint"],
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code_verifier": request.cookies[OKTA_VERIFIER_COOKIE],
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(token_request, timeout=10) as response:
            token_response = json.loads(response.read())
        access_token = token_response["access_token"]
        jwks_client = PyJWKClient(metadata["jwks_uri"])
        signing_key = jwks_client.get_signing_key_from_jwt(token_response["id_token"]).key
        claims = jwt.decode(
            token_response["id_token"],
            signing_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )
        if not secrets.compare_digest(claims["nonce"], request.cookies[OKTA_NONCE_COOKIE]):
            return okta_error_redirect(secure, "okta_nonce_invalid")

        userinfo_request = URLRequest(
            metadata["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        with urlopen(userinfo_request, timeout=10) as response:
            userinfo = json.loads(response.read())
        userinfo_error = userinfo_error_reason(claims, userinfo)
        if userinfo_error is not None:
            return okta_error_redirect(secure, userinfo_error)
        email = userinfo.get("email")
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            return okta_error_redirect(secure, "okta_user_not_linked")
    except (HTTPError, URLError, TimeoutError):
        return okta_error_redirect(secure, "okta_exchange_failed")
    except (ValueError, KeyError, TypeError, InvalidTokenError, jwt.PyJWTError):
        return okta_error_redirect(secure, "okta_token_invalid")

    app_token = create_access_token(user.id, user.email, user.role)
    redirect_uri_frontend = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")
    response = RedirectResponse(f"{redirect_uri_frontend}/#access_token={app_token}")
    clear_okta_cookies(response, secure)
    return response


@app.get("/api/auth/me", response_model=UserResponse)
def current_user_profile(user: User = Depends(get_current_user)):
    return user_response(user)


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
