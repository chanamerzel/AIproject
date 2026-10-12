from app import db


def get_user(user_id: str):
    return db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


def get_user_by_email(email: str):
    return db.fetch_one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
