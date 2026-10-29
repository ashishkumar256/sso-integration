# Northstar Flask Console

A responsive service overview UI backed by a small Flask app. The dashboard reports runtime details from the running process, and `/health` provides a JSON health check.

## Sign-in options

The login page offers both local username/password authentication and Okta. Local credentials are configured through environment variables and are not stored in a database. `LOCAL_ADMIN_EMAIL` and `LOCAL_ADMIN_PASSWORD` define an admin account; `LOCAL_USER_EMAIL` and `LOCAL_USER_PASSWORD` define a regular account. Defaults for the emails are `ashish@authmantra.com` and `poc@authmantra.com`; set strong unique passwords in `.env` before running the app.

Okta sign-in remains available in parallel. Its allowed identities default to the same two emails. Assign the `AuthMantra-Admins` Okta group to Ashish to grant admin access; an allowed user not in that group receives the regular user role.

Create an OIDC Web Application in Okta with Authorization Code enabled. Add this sign-in redirect URI:

```text
http://localhost:5000/authorization-code/callback
```

Set `OKTA_REDIRECT_URI` to this exact URI in `.env`, and add the identical value under the Okta app's **Sign-in redirect URIs**. For deployments, replace `localhost:5000` with the public hostname and exposed port. The value in the error message is the exact URI Okta rejected; it must appear exactly in that app's redirect URI list.

Add a `groups` claim to the ID token (or userinfo response) that includes the `AuthMantra-Admins` group. Copy the issuer URL, client ID, and client secret into `.env`:

```sh
cp .env.example .env
```

Set a long random `SECRET_KEY`, replace the Okta placeholders, set both local passwords, and do not commit `.env`. `OKTA_ALLOWED_EMAILS` is a comma-separated allowlist; `OKTA_ADMIN_GROUP` selects the Okta group that receives admin privileges. Local roles are fixed by the admin/user environment slots. For production, register the HTTPS callback URL and set `COOKIE_SECURE=true` to restrict session cookies to secure connections. Gunicorn access and error logs are written to container output; set `LOG_LEVEL` to adjust the Gunicorn log level.

## Run with Docker

```sh
docker compose up --build
```

Open `http://localhost:5000`. The health endpoint is available at `http://localhost:5000/health`. Stop the service with `Ctrl+C`; run `docker compose down` to remove its container.

## Run locally

Create and activate a virtual environment, configure the same environment variables as `.env`, then install dependencies and start Flask:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY='your-random-session-secret'
export OKTA_ISSUER='https://your-okta-domain.okta.com/oauth2/default'
export OKTA_REDIRECT_URI='http://localhost:5000/authorization-code/callback'
export OKTA_CLIENT_ID='your-client-id'
export OKTA_CLIENT_SECRET='your-client-secret'
export OKTA_ADMIN_GROUP='AuthMantra-Admins'
export OKTA_ALLOWED_EMAILS='ashish@authmantra.com,poc@authmantra.com'
export LOCAL_ADMIN_EMAIL='ashish@authmantra.com'
export LOCAL_ADMIN_PASSWORD='your-local-admin-password'
export LOCAL_USER_EMAIL='poc@authmantra.com'
export LOCAL_USER_PASSWORD='your-local-user-password'
python app.py
```

Register `http://localhost:5000/authorization-code/callback` as an additional Okta redirect URI for local development. Open `http://localhost:5000`. Set `SERVICE_NAME` to change the label shown in the dashboard and health response. Set `PORT` to change the local Flask port.
