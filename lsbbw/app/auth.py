import secrets
from fastapi import Request
from app.database import get_db


async def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get("lsbbw_user")
    if not token:
        return None
    db = get_db()
    row = db.execute(
        "SELECT u.* FROM users u "
        "JOIN user_sessions s ON u.id = s.user_id "
        "WHERE s.token = ? AND s.created_at > datetime('now', '-30 days')",
        (token,),
    ).fetchone()
    db.close()
    return dict(row) if row else None


def create_user_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db = get_db()
    db.execute("INSERT INTO user_sessions (token, user_id) VALUES (?, ?)", (token, user_id))
    db.commit()
    db.close()
    return token
