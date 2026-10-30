"""Run an interactive Okta OIDC login and print selected UserInfo claims.

Register http://127.0.0.1:8765/callback as a Login redirect URI in Okta first.
"""

import base64
import getpass
import hashlib
import json
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


REDIRECT_URI = "http://127.0.0.1:8765/callback"
CALLBACK_PATH = "/callback"


def load_dotenv_values():
    values = {}
    env_file = Path(__file__).with_name(".env")
    if not env_file.exists():
        return values
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def setting(name, dotenv, default=""):
    return os.environ.get(name) or dotenv.get(name) or default


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        self.server.callback = urllib.parse.parse_qs(parsed.query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><title>Okta check</title><body>Sign-in response received. "
            b"You can return to the terminal.</body></html>"
        )

    def log_message(self, _format, *_args):
        return


def post_form(url, data, headers):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def main():
    dotenv = load_dotenv_values()
    issuer = setting("OKTA_ISSUER", dotenv).rstrip("/")
    client_id = setting("OKTA_CLIENT_ID", dotenv)
    if not issuer or not client_id:
        raise SystemExit("Set OKTA_ISSUER and OKTA_CLIENT_ID in .env or the environment.")

    metadata_request = urllib.request.Request(
        f"{issuer}/.well-known/openid-configuration",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(metadata_request, timeout=15) as response:
        metadata = json.load(response)
    if metadata.get("issuer", "").rstrip("/") != issuer:
        raise SystemExit("The issuer in Okta discovery metadata does not match OKTA_ISSUER.")

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    challenge = challenge.rstrip(b"=").decode("ascii")
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    authorization_url = f"{metadata['authorization_endpoint']}?{query}"

    server = HTTPServer(("127.0.0.1", 8765), CallbackHandler)
    server.timeout = 300
    print("Opening Okta sign-in in your browser. Complete login to continue.")
    print(f"Callback URI to register in Okta: {REDIRECT_URI}")
    webbrowser.open(authorization_url)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join()
    server.server_close()

    callback = getattr(server, "callback", {})
    if not callback:
        raise SystemExit("Timed out waiting for the Okta callback.")
    if callback.get("state", [None])[0] != state:
        raise SystemExit("OAuth state did not match; aborting sign-in.")
    if callback.get("error"):
        raise SystemExit("Okta sign-in failed: " + callback["error"][0])
    code = callback.get("code", [None])[0]
    if not code:
        raise SystemExit("Okta callback did not contain an authorization code.")

    client_secret = getpass.getpass("Okta client secret: ")
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    auth_method = setting("OKTA_TOKEN_AUTH_METHOD", dotenv, "client_secret_basic")
    headers = {"Accept": "application/json"}
    if auth_method == "client_secret_post":
        token_data.update(client_id=client_id, client_secret=client_secret)
    elif auth_method == "client_secret_basic":
        credentials = f"{client_id}:{client_secret}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode("ascii")
    else:
        raise SystemExit("OKTA_TOKEN_AUTH_METHOD must be client_secret_basic or client_secret_post.")

    try:
        tokens = post_form(metadata["token_endpoint"], token_data, headers)
        userinfo_request = urllib.request.Request(
            metadata["userinfo_endpoint"],
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(userinfo_request, timeout=20) as response:
            claims = json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Okta returned HTTP {error.code}; verify the app, grant, and token auth method.") from None
    except urllib.error.URLError as error:
        raise SystemExit(f"Could not reach Okta: {error.reason}") from None

    print(json.dumps({
        "email": claims.get("email"),
        "email_verified": claims.get("email_verified", "<not returned>"),
    }, indent=2))


if __name__ == "__main__":
    main()