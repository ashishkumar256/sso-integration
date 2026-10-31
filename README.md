# AuthMantra three-tier starter

A local three-container sign-in app with a React frontend, FastAPI backend, and PostgreSQL database. The API stores password hashes, verifies credentials, and returns a short-lived JWT containing the user's role.

## Start with Docker Compose

1. Copy `.env.example` to `.env` and change the local secrets if needed.
2. Start the stack from this directory:

   ```sh
   docker compose up --build
   ```

3. Open `http://localhost:3000`.

The API health endpoint is `http://localhost:8000/api/health`. Compose waits for PostgreSQL health before starting the API, and for API health before starting the frontend. PostgreSQL data persists in the `postgres_data` volume.

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Admin | `ashish@authmantra.com` | `AdminPass123!` |
| POC user | `poc@authmantra.com` | `TestPass123!` |

These are development-only defaults. Set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `TEST_USER_EMAIL`, and `TEST_USER_PASSWORD` in `.env` before starting. At each backend startup, the idempotent seeder checks for the configured addresses and only inserts accounts that are absent. It migrates the earlier demo addresses (`admin@example.com` and `test@example.com`) to the new addresses if the configured accounts do not exist; when both old and new seeded identities exist, it removes the old seeded row. It does not reset passwords or overwrite an already-existing account. For a clean local reset, run `docker compose down -v` (this deletes the local database volume).

After signing in, administrators can add, edit, and delete users. The POC account is read-only, and the API enforces that restriction regardless of the UI. Administrators cannot delete their own account or demote/delete the last administrator.

## Local development

The containers are the recommended path. To run a service outside Compose, install the packages in `backend/requirements.txt`, provide a PostgreSQL `DATABASE_URL`, and start the backend with `uvicorn app.main:app --reload --app-dir backend`. Run the frontend with `cd frontend && npm install && npm run dev`; set `VITE_API_URL` to the reachable backend URL.

Backend tests use an isolated in-memory SQLite database:

```sh
cd backend
pip install -r requirements-dev.txt
pytest
```

## Okta sign-in

Create an OIDC Web Application in the Okta Admin Console. Add `http://localhost:8000/api/auth/okta/callback` as a sign-in redirect URI and enable Authorization Code. Set `OKTA_ISSUER` to the authorization server issuer URL (commonly `https://{yourOktaDomain}/oauth2/default`), then set `OKTA_CLIENT_ID` and `OKTA_CLIENT_SECRET` in `.env`. The Okta sign-in button is enabled when the client ID is set. Rebuild with `docker compose up --build` after changing frontend build settings.

The callback requires an Okta-verified email matching an existing local user. Roles remain controlled by the local user directory; an unknown email is not automatically provisioned. Use HTTPS for non-local deployments and set `OKTA_REDIRECT_URI` to the exact callback URI registered in Okta.

## Configuration and security

Compose publishes the frontend on port 3000 and the API on port 8000. `VITE_API_URL` is baked into the frontend build. Replace `JWT_SECRET` and all demo credentials before using this outside a local development environment. The demo credentials are intentionally displayed on the sign-in page for local testing; remove that helper for a real deployment. This starter issues JWTs but does not yet provide protected application routes or refresh tokens.
