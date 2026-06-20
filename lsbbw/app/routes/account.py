import re
from passlib.context import CryptContext
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import get_db
from app.auth import get_current_user, create_user_session

router = APIRouter(prefix="/account")
templates = Jinja2Templates(directory="app/templates")
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if await get_current_user(request):
        return RedirectResponse("/account/dashboard", status_code=302)
    return templates.TemplateResponse(request, "account/signup.html", {"error": None, "current_user": None})


@router.post("/signup", response_class=HTMLResponse)
async def signup_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    email = email.strip().lower()

    if not _EMAIL_RE.match(email):
        return templates.TemplateResponse(request, "account/signup.html", {
            "error": "Enter a valid email address.", "current_user": None,
        })
    if len(password) < 8:
        return templates.TemplateResponse(request, "account/signup.html", {
            "error": "Password must be at least 8 characters.", "current_user": None,
        })
    if len(password.encode()) > 72:
        return templates.TemplateResponse(request, "account/signup.html", {
            "error": "Password is too long (max 72 characters).", "current_user": None,
        })
    if password != password2:
        return templates.TemplateResponse(request, "account/signup.html", {
            "error": "Passwords don't match.", "current_user": None,
        })

    db = get_db()
    if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        db.close()
        return templates.TemplateResponse(request, "account/signup.html", {
            "error": "An account with that email already exists.", "current_user": None,
        })

    cur = db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        (email, pwd_ctx.hash(password)),
    )
    user_id = cur.lastrowid
    db.commit()
    db.close()

    token = create_user_session(user_id)
    resp = RedirectResponse("/account/dashboard", status_code=302)
    resp.set_cookie("lsbbw_user", token, httponly=True, samesite="lax", max_age=2592000)
    return resp


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if await get_current_user(request):
        return RedirectResponse("/account/dashboard", status_code=302)
    return templates.TemplateResponse(request, "account/login.html", {"error": None, "current_user": None})


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()

    if not row or not pwd_ctx.verify(password, row["password_hash"]):
        return templates.TemplateResponse(request, "account/login.html", {
            "error": "Incorrect email or password.", "current_user": None,
        })

    token = create_user_session(row["id"])
    resp = RedirectResponse("/account/dashboard", status_code=302)
    resp.set_cookie("lsbbw_user", token, httponly=True, samesite="lax", max_age=2592000)
    return resp


@router.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("lsbbw_user")
    if token:
        db = get_db()
        db.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        db.commit()
        db.close()
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("lsbbw_user")
    return resp


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse("/account/login", status_code=302)
    return templates.TemplateResponse(request, "account/dashboard.html", {"current_user": user})
