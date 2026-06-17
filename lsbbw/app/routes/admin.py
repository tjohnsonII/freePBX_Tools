import os
import secrets
from fastapi import APIRouter, Request, Form, Cookie, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import get_db

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")

ADMIN_PASSWORD = os.environ.get("LSBBW_ADMIN_PASS", "changeme123")


def _check_auth(session: str | None) -> bool:
    if not session:
        return False
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM admin_sessions WHERE token=? "
        "AND created_at > datetime('now','-8 hours')",
        (session,),
    ).fetchone()
    db.close()
    return row is not None


# ── Login ───────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, password: str = Form(...)):
    if not secrets.compare_digest(password, ADMIN_PASSWORD):
        return templates.TemplateResponse("admin/login.html", {
            "request": request,
            "error": "Wrong password.",
        })
    token = secrets.token_urlsafe(32)
    db = get_db()
    db.execute("INSERT INTO admin_sessions (token) VALUES (?)", (token,))
    db.commit()
    db.close()
    resp = RedirectResponse("/admin/dashboard", status_code=302)
    resp.set_cookie("lsbbw_admin", token, httponly=True, samesite="lax", max_age=28800)
    return resp


@router.get("/logout")
async def logout(lsbbw_admin: str | None = Cookie(None)):
    if lsbbw_admin:
        db = get_db()
        db.execute("DELETE FROM admin_sessions WHERE token=?", (lsbbw_admin,))
        db.commit()
        db.close()
    resp = RedirectResponse("/admin/login", status_code=302)
    resp.delete_cookie("lsbbw_admin")
    return resp


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, lsbbw_admin: str | None = Cookie(None), status: str = "pending"):
    if not _check_auth(lsbbw_admin):
        return RedirectResponse("/admin/login", status_code=302)

    db = get_db()
    videos = db.execute(
        "SELECT * FROM videos WHERE status=? ORDER BY created_at DESC LIMIT 100",
        (status,),
    ).fetchall()
    counts = {
        "pending":  db.execute("SELECT COUNT(*) FROM videos WHERE status='pending'").fetchone()[0],
        "approved": db.execute("SELECT COUNT(*) FROM videos WHERE status='approved'").fetchone()[0],
        "rejected": db.execute("SELECT COUNT(*) FROM videos WHERE status='rejected'").fetchone()[0],
    }
    db.close()

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "videos": videos,
        "counts": counts,
        "active_status": status,
    })


# ── Actions ──────────────────────────────────────────────────────────────────

@router.post("/approve/{video_id}")
async def approve(video_id: int, lsbbw_admin: str | None = Cookie(None)):
    if not _check_auth(lsbbw_admin):
        raise HTTPException(status_code=403)
    db = get_db()
    db.execute("UPDATE videos SET status='approved' WHERE id=?", (video_id,))
    db.commit()
    db.close()
    return RedirectResponse("/admin/dashboard", status_code=302)


@router.post("/reject/{video_id}")
async def reject(video_id: int, lsbbw_admin: str | None = Cookie(None)):
    if not _check_auth(lsbbw_admin):
        raise HTTPException(status_code=403)
    db = get_db()
    db.execute("UPDATE videos SET status='rejected' WHERE id=?", (video_id,))
    db.commit()
    db.close()
    return RedirectResponse("/admin/dashboard", status_code=302)


@router.post("/delete/{video_id}")
async def delete(video_id: int, lsbbw_admin: str | None = Cookie(None)):
    if not _check_auth(lsbbw_admin):
        raise HTTPException(status_code=403)
    db = get_db()
    row = db.execute("SELECT file_path FROM videos WHERE id=?", (video_id,)).fetchone()
    if row and row["file_path"]:
        full = f"/var/www/lsbbw{row['file_path']}"
        if os.path.exists(full):
            os.remove(full)
    db.execute("DELETE FROM videos WHERE id=?", (video_id,))
    db.commit()
    db.close()
    return RedirectResponse("/admin/dashboard", status_code=302)
