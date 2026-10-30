# Northstar Flask Console

A Flask service dashboard with Okta OIDC and optional local username/password sign-in. The dashboard shows runtime information, `/health` provides a public JSON health check for Docker, and `/admin` is restricted to admin-role sessions. No database is used.

## Authentication Model

The login page offers two independent methods:

- **Okta OIDC:** Okta authenticates the user. Flask then checks the UserInfo response, requires `email_verified` to be exactly `true`, checks `OKTA_ALLOWED_EMAILS`, and assigns the admin role when the returned `groups` claim includes `OKTA_ADMIN_GROUP`. An authenticated Okta user is not automatically authorized by this app: Okta app assignment and Flask's allowlist/group checks are separate gates.
- **Local credentials:** Optional development accounts are configured by `LOCAL_ADMIN_EMAIL`/`LOCAL_ADMIN_PASSWORD` and `LOCAL_USER_EMAIL`/`LOCAL_USER_PASSWORD`. Their roles are fixed by those configuration slots. Credentials are environment variables, not database records; use strong values and do not use this mechanism for production account management.

Default allowlist and local account emails are `ashish@authmantra.com` and `poc@authmantra.com`. `OKTA_ALLOWED_EMAILS` is a comma-separated email allowlist. It is an app-level restriction, not an Okta user directory. To support many users, prefer Okta app assignment and group-based authorization instead of maintaining an email list.

## Okta Setup

Create an **OIDC Web Application** in Okta and enable the **Authorization Code** grant. Configure a sign-in redirect URI for every flow you use. Each URI must be registered under that exact OIDC app's **Sign-in redirect URIs**, and must match the request exactly, including scheme, hostname, port, and path. Do not put these in sign-out URIs or Trusted Origins.

For the Flask app:

```text
http://localhost:5000/authorization-code/callback
```

Set the same value in `OKTA_REDIRECT_URI`. For a deployed app, use its public HTTPS hostname in both places.

The optional UserInfo helper uses a different callback. Register this additional URI if you run it:

```text
http://127.0.0.1:8765/callback
```

Configure the `default` authorization server with an active access policy and rule. In the Okta Admin Console, go to **Security → API → Authorization Servers → default → Access Policies**. If no suitable policy exists, create one; otherwise edit the existing policy. Add or edit an active rule whose **Action** is **Allow**, and configure it to match the Flask OIDC client, the test user or group, and the **Authorization Code** grant. Allow the scopes requested by this app: `openid`, `profile`, and `email`. In our setup, the default authorization server had no applicable policy/rule, which caused Okta's “Policy evaluation failed for this request” error. Ensure the user is assigned to the OIDC app as well; app assignment and authorization-server policy are separate checks.

Add a `groups` claim that is returned by UserInfo, with the admin group included. Set `OKTA_ADMIN_GROUP` to the exact group name. Add Ashish to that group for admin access. An allowed user not in the group receives the regular user role. If groups are missing from UserInfo, the login can still succeed but the user will be assigned the regular role.

### Email Verification Claim

The app fetches claims from Okta's **UserInfo endpoint** using the access token obtained during the authorization-code flow. It does not rely on the ID token payload for `email_verified`. The callback requires UserInfo to return `email_verified: true`; false or missing values are rejected. `email` identifies the user, and `groups` is used for role assignment.

The access token is used to call UserInfo; it is not the place to inspect identity claims. In Okta Token Preview, `email_verified` may not appear in the ID token payload even when UserInfo returns it. The standalone helper below performs the flow and prints just `email` and `email_verified` without requiring you to obtain an access token manually.

An Okta user being **Active** means the account can sign in; do not treat that status as proof that the email claim is verified. Check the user profile/status in **Directory → People**, and use the UserInfo helper to see the claim actually returned to this client. An already-active user may not have an activation resend action.

## Configure Environment

Start from the example:

```sh
cp .env.example .env
```

Set a unique, long random `SECRET_KEY`; set the Okta issuer, client ID, client secret, and callback; and set strong local passwords if local login is enabled. `OKTA_ISSUER` should be the issuer from the authorization server's discovery document, for example `https://your-org.okta.com/oauth2/default`. Do not use the Okta Admin Console URL as the issuer.

Never commit `.env` or paste credentials, authorization codes, access tokens, ID tokens, or session cookies into logs or chat. Rotate any client secret that has been exposed. Keep `COOKIE_SECURE=false` only for local HTTP development; set it to `true` behind HTTPS.

## Run With Docker

```sh
docker compose up -d --build
```

Open `http://localhost:5000`. The public health endpoint is `http://localhost:5000/health`. Follow logs with:

```sh
docker compose logs -f web
```

Gunicorn access and error logs, plus Flask logs, are sent to Docker output. Access logs omit query strings so authorization codes are not recorded. Set `LOG_LEVEL=debug` to enable Flask/Gunicorn debug output. At debug level, the app logs the full UserInfo claims, which may contain personal data; use this only temporarily and return to `LOG_LEVEL=info` afterward. `docker compose down` stops and removes the container.

## Inspect UserInfo

Run the local helper from the project directory:

```sh
python3 check_okta_userinfo.py
```

It reads `OKTA_ISSUER` and `OKTA_CLIENT_ID` from `.env` or the environment, opens Okta sign-in in a browser, waits for the local callback, exchanges the authorization code using PKCE, calls UserInfo, and prints only `email` and `email_verified`. It prompts for the client secret without echoing it. It cannot bypass Okta login or MFA. Register `http://127.0.0.1:8765/callback` on the same OIDC app before running it. The helper uses the client's configured token endpoint authentication method; the default is `client_secret_basic` and can be changed with `OKTA_TOKEN_AUTH_METHOD=client_secret_post` if the app is configured that way.

## Common Okta Errors

- **`redirect_uri` is not a Login redirect URI:** Register the exact callback URI in the same OIDC app whose client ID the request uses. `localhost` and `127.0.0.1` are different; the Flask callback and helper callback are also different.
- **Authorization server policy evaluation failed:** Check that the `default` authorization server has an active policy and matching rule for this client, user, Authorization Code grant, and requested scopes. Also verify the user is assigned to the app.
- **Forbidden: email is not verified:** The Flask callback requires `email_verified: true` in UserInfo. Check the UserInfo response with the helper; an ID token without this claim does not prove UserInfo omitted it.
- **Login succeeds but user has regular role:** Verify that UserInfo returns the `groups` claim and that it contains the exact `OKTA_ADMIN_GROUP` value.

## Run Locally

Create a virtual environment, install dependencies, configure the same required values as `.env`, then start Flask:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Register `http://localhost:5000/authorization-code/callback` in Okta for local Flask development. Set `PORT` to change Flask's local port and update both the registered callback and `OKTA_REDIRECT_URI`. Set `SERVICE_NAME` to change the label on the dashboard and health response.
