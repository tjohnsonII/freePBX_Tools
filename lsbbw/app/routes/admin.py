import os
import secrets
import httpx
from urllib.parse import urlencode
from fastapi import APIRouter, Request, Form, Cookie, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import get_db

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")

ADMIN_PASSWORD = os.environ.get("LSBBW_ADMIN_PASS", "changeme123")
CATEGORIES = ["General", "Music Videos", "Freestyles", "Thick Thursdays", "Fan Favorites", "Comedy", "Other"]

# ── Keycloak OIDC config ──────────────────────────────────────────────────────
_KC_URL    = os.environ.get("KEYCLOAK_URL", "")
_KC_REALM  = os.environ.get("KEYCLOAK_REALM", "internal-tools")
_KC_ID     = os.environ.get("KEYCLOAK_CLIENT_ID", "lsbbw-admin")
_KC_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")
_KC_REDIR  = os.environ.get("KEYCLOAK_REDIRECT_URI", "https://ilovelsbbw.com/admin/callback")


def _keycloak_enabled() -> bool:
    return bool(_KC_URL and _KC_SECRET)


def _keycloak_auth_url(state: str) -> str:
    base = f"{_KC_URL}/realms/{_KC_REALM}/protocol/openid-connect/auth"
    return base + "?" + urlencode({
        "client_id": _KC_ID,
        "redirect_uri": _KC_REDIR,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    })


async def _exchange_code(code: str) -> dict | None:
    token_url = f"{_KC_URL}/realms/{_KC_REALM}/protocol/openid-connect/token"
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _KC_REDIR,
            "client_id": _KC_ID,
            "client_secret": _KC_SECRET,
        })
        if resp.status_code == 200:
            return resp.json()
    return None


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


def _create_session() -> str:
    token = secrets.token_urlsafe(32)
    db = get_db()
    db.execute("INSERT INTO admin_sessions (token) VALUES (?)", (token,))
    db.commit()
    db.close()
    return token


# ── Login ────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, local: str = ""):
    # ?local=1 bypasses Keycloak for emergency password login
    if _keycloak_enabled() and not local:
        state = secrets.token_urlsafe(16)
        resp = RedirectResponse(_keycloak_auth_url(state), status_code=302)
        resp.set_cookie("lsbbw_oidc_state", state, httponly=True, samesite="lax", max_age=300)
        return resp
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, password: str = Form(...)):
    if not secrets.compare_digest(password, ADMIN_PASSWORD):
        return templates.TemplateResponse(request, "admin/login.html", {"error": "Wrong password."})
    token = _create_session()
    resp = RedirectResponse("/admin/dashboard", status_code=302)
    resp.set_cookie("lsbbw_admin", token, httponly=True, samesite="lax", max_age=28800)
    return resp


# ── Keycloak callback ─────────────────────────────────────────────────────────

@router.get("/callback")
async def oidc_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
):
    if error:
        return templates.TemplateResponse(request, "admin/login.html", {
            "error": f"Keycloak error: {error_description or error}"
        })

    stored_state = request.cookies.get("lsbbw_oidc_state", "")
    if not state or not secrets.compare_digest(state, stored_state):
        return templates.TemplateResponse(request, "admin/login.html", {
            "error": "State mismatch — please try logging in again."
        })

    tokens = await _exchange_code(code)
    if not tokens or "access_token" not in tokens:
        return templates.TemplateResponse(request, "admin/login.html", {
            "error": "Token exchange failed — check client secret and redirect URI."
        })

    session_token = _create_session()
    resp = RedirectResponse("/admin/dashboard", status_code=302)
    resp.set_cookie("lsbbw_admin", session_token, httponly=True, samesite="lax", max_age=28800)
    resp.delete_cookie("lsbbw_oidc_state")
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
async def dashboard(
    request: Request,
    lsbbw_admin: str | None = Cookie(None),
    status: str = "pending",
    q: str = "",
    category: str = "",
):
    if not _check_auth(lsbbw_admin):
        return RedirectResponse("/admin/login", status_code=302)

    db = get_db()

    counts = {
        "pending":  db.execute("SELECT COUNT(*) FROM videos WHERE status='pending'").fetchone()[0],
        "approved": db.execute("SELECT COUNT(*) FROM videos WHERE status='approved'").fetchone()[0],
        "rejected": db.execute("SELECT COUNT(*) FROM videos WHERE status='rejected'").fetchone()[0],
    }
    total_views = db.execute("SELECT COALESCE(SUM(views),0) FROM videos WHERE status='approved'").fetchone()[0]
    today_subs  = db.execute(
        "SELECT COUNT(*) FROM videos WHERE date(created_at)=date('now')"
    ).fetchone()[0]

    where = "WHERE status=?"
    params: list = [status]
    if q:
        where += " AND title LIKE ?"
        params.append(f"%{q}%")
    if category:
        where += " AND category=?"
        params.append(category)

    videos = db.execute(
        f"SELECT * FROM videos {where} ORDER BY created_at DESC LIMIT 200",
        params,
    ).fetchall()
    db.close()

    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "videos": videos,
        "counts": counts,
        "total_views": total_views,
        "today_subs": today_subs,
        "active_status": status,
        "categories": CATEGORIES,
        "q": q,
        "active_cat": category,
    })


# ── Edit ─────────────────────────────────────────────────────────────────────

@router.get("/edit/{video_id}", response_class=HTMLResponse)
async def edit_page(request: Request, video_id: int, lsbbw_admin: str | None = Cookie(None)):
    if not _check_auth(lsbbw_admin):
        return RedirectResponse("/admin/login", status_code=302)
    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    db.close()
    if not video:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "admin/edit.html", {
        "video": video,
        "categories": CATEGORIES,
        "saved": False,
    })


@router.post("/edit/{video_id}", response_class=HTMLResponse)
async def edit_post(
    request: Request,
    video_id: int,
    lsbbw_admin: str | None = Cookie(None),
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("General"),
    thumbnail: str = Form(""),
):
    if not _check_auth(lsbbw_admin):
        raise HTTPException(status_code=403)
    if category not in CATEGORIES:
        category = "General"
    db = get_db()
    db.execute(
        "UPDATE videos SET title=?, description=?, category=?, thumbnail=? WHERE id=?",
        (title.strip()[:200], description.strip()[:2000], category,
         thumbnail.strip() or None, video_id),
    )
    db.commit()
    video = db.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    db.close()
    return templates.TemplateResponse(request, "admin/edit.html", {
        "video": video,
        "categories": CATEGORIES,
        "saved": True,
    })


# ── Bulk actions ─────────────────────────────────────────────────────────────

@router.post("/bulk", response_class=HTMLResponse)
async def bulk_action(
    request: Request,
    lsbbw_admin: str | None = Cookie(None),
):
    if not _check_auth(lsbbw_admin):
        raise HTTPException(status_code=403)
    form = await request.form()
    action = form.get("bulk_action", "")
    ids = form.getlist("selected")
    if ids and action in ("approve", "reject", "delete"):
        db = get_db()
        for vid_id in ids:
            if action == "delete":
                row = db.execute("SELECT file_path FROM videos WHERE id=?", (vid_id,)).fetchone()
                if row and row["file_path"]:
                    full = f"/var/www/lsbbw{row['file_path']}"
                    if os.path.exists(full):
                        os.remove(full)
                db.execute("DELETE FROM videos WHERE id=?", (vid_id,))
            else:
                new_status = "approved" if action == "approve" else "rejected"
                db.execute("UPDATE videos SET status=? WHERE id=?", (new_status, vid_id))
        db.commit()
        db.close()
    return RedirectResponse("/admin/dashboard", status_code=302)


# ── Approve all pending ───────────────────────────────────────────────────────

@router.post("/approve-all-pending")
async def approve_all_pending(lsbbw_admin: str | None = Cookie(None)):
    if not _check_auth(lsbbw_admin):
        raise HTTPException(status_code=403)
    db = get_db()
    db.execute("UPDATE videos SET status='approved' WHERE status='pending'")
    db.commit()
    db.close()
    return RedirectResponse("/admin/dashboard?status=approved", status_code=302)


# ── Single actions ────────────────────────────────────────────────────────────

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
