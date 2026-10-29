"""Google sign-in (OpenID Connect) through Authlib. Off unless both client keys are set."""

from flask import current_app

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"


def google_enabled(app=None) -> bool:
    config = (app or current_app).config
    return bool(config.get("GOOGLE_CLIENT_ID") and config.get("GOOGLE_CLIENT_SECRET"))


def init_google(app):
    if not google_enabled(app):
        return
    from authlib.integrations.flask_client import OAuth

    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url=GOOGLE_METADATA_URL,
        client_kwargs={"scope": "openid email profile"},
    )
    app.extensions["google_oauth"] = oauth.google


def start_login(redirect_uri: str):
    return current_app.extensions["google_oauth"].authorize_redirect(redirect_uri)


def finish_login() -> dict:
    client = current_app.extensions["google_oauth"]
    token = client.authorize_access_token()
    info = token.get("userinfo") or client.userinfo(token=token)
    return {
        "email": (info.get("email") or "").strip().lower(),
        "name": info.get("name") or "",
        "email_verified": bool(info.get("email_verified")),
    }
