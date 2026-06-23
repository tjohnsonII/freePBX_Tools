from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import get_db
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

CATEGORIES = ["General", "Music Videos", "Freestyles", "Thick Thursdays", "Fan Favorites", "Comedy", "Other"]
PER_PAGE = 24


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, category: str = "", page: int = 1):
    user = await get_current_user(request)
    db = get_db()
    offset = (page - 1) * PER_PAGE

    where = "WHERE status='approved'"
    params: list = []
    if category and category in CATEGORIES:
        where += " AND category=?"
        params.append(category)

    total = db.execute(f"SELECT COUNT(*) FROM videos {where}", params).fetchone()[0]
    videos = db.execute(
        f"SELECT * FROM videos {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [PER_PAGE, offset],
    ).fetchall()
    db.close()

    pages = (total + PER_PAGE - 1) // PER_PAGE
    return templates.TemplateResponse(request, "index.html", {
        "videos": videos,
        "categories": CATEGORIES,
        "active_cat": category,
        "page": page,
        "pages": pages,
        "current_user": user,
    })


@router.get("/v/{video_id}", response_class=HTMLResponse)
async def video_page(request: Request, video_id: int):
    user = await get_current_user(request)
    db = get_db()
    video = db.execute(
        "SELECT * FROM videos WHERE id=? AND status='approved'", (video_id,)
    ).fetchone()
    if not video:
        db.close()
        raise HTTPException(status_code=404, detail="Video not found")

    db.execute("UPDATE videos SET views = views + 1 WHERE id=?", (video_id,))
    db.commit()

    related = db.execute(
        "SELECT * FROM videos WHERE status='approved' AND category=? AND id!=? ORDER BY views DESC LIMIT 8",
        (video["category"], video_id),
    ).fetchall()
    db.close()

    return templates.TemplateResponse(request, "video.html", {
        "video": video,
        "related": related,
        "current_user": user,
    })
