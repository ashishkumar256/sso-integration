import os
import platform
import secrets
import time
from functools import wraps
from datetime import datetime, timezone
from hmac import compare_digest

from authlib.integrations.flask_client import OAuth
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)
STARTED_AT = time.monotonic()
SERVICE_NAME = os.environ.get("SERVICE_NAME", "Flask service")
OKTA_ISSUER = os.environ.get("OKTA_ISSUER", "").rstrip("/")
OKTA_REDIRECT_URI = os.environ.get("OKTA_REDIRECT_URI", "").strip()
OKTA_ADMIN_GROUP = os.environ.get("OKTA_ADMIN_GROUP", "AuthMantra-Admins")
OKTA_ALLOWED_EMAILS = {
    email.strip().lower()
    for email in os.environ.get(
        "OKTA_ALLOWED_EMAILS",
        "ashish@authmantra.com,poc@authmantra.com",
    ).split(",")
    if email.strip()
}
oauth = OAuth(app)
if OKTA_ISSUER:
    oauth.register(
        name="okta",
        client_id=os.environ.get("OKTA_CLIENT_ID"),
        client_secret=os.environ.get("OKTA_CLIENT_SECRET"),
        server_metadata_url=f"{OKTA_ISSUER}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email"},
    )


def okta_is_configured():
    return bool(
        OKTA_ISSUER
        and os.environ.get("OKTA_CLIENT_ID")
        and os.environ.get("OKTA_CLIENT_SECRET")
    )


def local_users():
    users = {}
    for role, prefix in (("admin", "LOCAL_ADMIN"), ("user", "LOCAL_USER")):
        email = os.environ.get(f"{prefix}_EMAIL", "").strip().lower()
        password = os.environ.get(f"{prefix}_PASSWORD", "")
        if email and password:
            users[email] = {"role": role, "password": password}
    return users


def csrf_token():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def require_csrf():
    token = session.get("csrf_token", "")
    submitted = request.form.get("csrf_token", "")
    if not token or not compare_digest(token, submitted):
        abort(400)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("email"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@app.get("/login")
def login():
    return render_template(
        "login.html",
        okta_configured=okta_is_configured(),
        local_configured=bool(local_users()),
    )


@app.get("/login/okta")
def login_okta():
    if not okta_is_configured():
        abort(503)
    redirect_uri = OKTA_REDIRECT_URI or url_for("auth_callback", _external=True)
    app.logger.info("Starting Okta sign-in with redirect URI %s", redirect_uri)
    return oauth.okta.authorize_redirect(redirect_uri)


@app.post("/login/local")
def login_local():
    require_csrf()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    user = local_users().get(email)
    if user and compare_digest(password, user["password"]):
        session.clear()
        session["email"] = email
        session["role"] = user["role"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        app.logger.info("Local sign-in succeeded for %s with role %s", email, user["role"])
        return redirect(url_for("dashboard"))
    app.logger.warning("Rejected local sign-in for %s", email or "<missing>")
    abort(401)


@app.get("/authorization-code/callback")
def auth_callback():
    if not okta_is_configured():
        abort(503)
    app.logger.info("Received Okta authorization callback")
    token = oauth.okta.authorize_access_token()
    claims = token.get("userinfo") or oauth.okta.userinfo()
    email = str(claims.get("email", "")).strip().lower()
    groups = claims.get("groups", [])
    if email not in OKTA_ALLOWED_EMAILS:
        app.logger.warning("Rejected Okta sign-in for email outside the configured allowlist: %s", email or "<missing>")
        abort(403, description="This Okta account is not permitted to access this application.")
    role = "admin" if OKTA_ADMIN_GROUP in groups else "user"
    session.clear()
    session["email"] = email
    session["role"] = role
    session["csrf_token"] = secrets.token_urlsafe(32)
    app.logger.info("Okta sign-in succeeded for %s with role %s", email, role)
    return redirect(url_for("dashboard"))


@app.post("/logout")
@login_required
def logout():
    require_csrf()
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    uptime_seconds = int(time.monotonic() - STARTED_AT)
    return render_template(
        "dashboard.html",
        service_name=SERVICE_NAME,
        python_version=platform.python_version(),
        platform_name=platform.system(),
        uptime_seconds=uptime_seconds,
        checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        current_email=session["email"],
        current_role=session["role"],
    )


@app.get("/admin")
@admin_required
def admin():
    return render_template(
        "admin.html",
        allowed_emails=sorted(OKTA_ALLOWED_EMAILS),
        local_emails=sorted(local_users()),
        admin_group=OKTA_ADMIN_GROUP,
        current_email=session["email"],
    )


@app.get("/health")
def health():
    return jsonify(
        status="healthy",
        service=SERVICE_NAME,
        uptime_seconds=int(time.monotonic() - STARTED_AT),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))