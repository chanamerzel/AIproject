import uuid

from werkzeug.security import generate_password_hash

from app.event_store import EventStore
from app.queries.identity import get_user_by_email

ALLOWED_ROLES = {"candidate", "hr", "hiring_manager"}


def register_user(email: str, password: str, full_name: str, role: str) -> str:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("אימייל לא תקין")
    if not full_name or not full_name.strip():
        raise ValueError("יש להזין שם מלא")
    if not password or len(password) < 6:
        raise ValueError("סיסמה חייבת לפחות 6 תווים")
    if role not in ALLOWED_ROLES:
        raise ValueError("תפקיד לא חוקי")
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
        },
    )
    return user_id
