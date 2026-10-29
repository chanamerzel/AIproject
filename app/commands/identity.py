import secrets
import uuid

from werkzeug.security import generate_password_hash

from app.event_store import EventStore
from app.queries.identity import get_user_by_email
from app.security import STAFF_ROLES, door_mismatch

ALLOWED_ROLES = {"candidate", *STAFF_ROLES}
AUTH_PROVIDERS = {"password", "google"}


def register_user(
    email: str,
    password: str,
    full_name: str,
    role: str,
    auth_provider: str = "password",
) -> str:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("אימייל לא תקין")
    if not full_name or not full_name.strip():
        raise ValueError("יש להזין שם מלא")
    if not password or len(password) < 6:
        raise ValueError("סיסמה חייבת לפחות 6 תווים")
    if role not in ALLOWED_ROLES:
        raise ValueError("תפקיד לא חוקי")
    if auth_provider not in AUTH_PROVIDERS:
        raise ValueError("ספק התחברות לא חוקי")
    if get_user_by_email(email):
        raise ValueError("האימייל כבר רשום")
    user_id = str(uuid.uuid4())
    EventStore.append(
        "UserRegistered",
        "User",
        user_id,
        {
            "email": email,
            "password_hash": generate_password_hash(password),
            "full_name": full_name.strip(),
            "role": role,
            "auth_provider": auth_provider,
        },
    )
    return user_id


def sign_in_with_google(email: str, full_name: str, email_verified: bool, door: str, staff_role: str | None) -> str:
    """Return the user id for a Google identity, registering it on first sign-in."""
    if not email_verified:
        raise ValueError("Google לא אישר את כתובת האימייל")
    existing = get_user_by_email(email or "")
    if existing:
        problem = door_mismatch(existing["role"], door)
        if problem:
            raise ValueError(problem)
        return existing["id"]
    if door == "staff":
        if staff_role not in STAFF_ROLES:
            raise ValueError("יש לבחור תפקיד בצוות הגיוס")
        role = staff_role
    else:
        role = "candidate"
    name = (full_name or "").strip() or (email or "").split("@")[0]
    # Google accounts get an unguessable password, so the password form never opens them.
    return register_user(email, secrets.token_urlsafe(32), name, role, auth_provider="google")
