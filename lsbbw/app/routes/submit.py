import os
import uuid
import subprocess
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import get_db
from app.embed import parse_embed

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

CATEGORIES = ["General", "Music Videos", "Freestyles", "Thick Thursdays", "Fan Favorites", "Comedy", "Other"]
UPLOAD_DIR = os.environ.get("LSBBW_UPLOADS", "/var/www/lsbbw/app/static/uploads")
THUMB_DIR  = os.environ.get("LSBBW_THUMBS",  "/var/www/lsbbw/app/static/thumbnails")
MAX_UPLOAD_MB = 500
ALLOWED_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}


def _make_thumbnail(video_path: str, thumb_name: str) -> str | None:
    """Extract a frame at 3s using FFmpeg. Returns web path or None on failure."""
    out = os.path.join(THUMB_DIR, thumb_name)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", "00:00:03",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "4",
                "-vf", "scale=480:-1",
                out,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and os.path.exists(out):
            return f"/static/thumbnails/{thumb_name}"
    except Exception:
        pass
    return None


@router.get("/submit", response_class=HTMLResponse)
async def submit_form(request: Request):
    return templates.TemplateResponse(request, "submit.html", {
        "categories": CATEGORIES,
        "error": None,
    })


@router.post("/submit", response_class=HTMLResponse)
async def submit_post(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("General"),
    submitter: str = Form("Anonymous"),
    embed_url: str = Form(""),
    video_file: UploadFile | None = File(None),
):
    title = title.strip()[:200]
    submitter = submitter.strip()[:80] or "Anonymous"
    description = description.strip()[:2000]

    if category not in CATEGORIES:
        category = "General"

    # ── Embed URL path ──────────────────────────────────────────────────────
    if embed_url.strip():
        parsed = parse_embed(embed_url.strip())
        if not parsed:
            return templates.TemplateResponse("submit.html", {
                "request": request,
                "categories": CATEGORIES,
                "error": "Unsupported URL. Paste a YouTube, Instagram, TikTok, or Twitter/X link.",
            })
        db = get_db()
        db.execute(
            "INSERT INTO videos (title, description, category, type, embed_url, thumbnail, submitter) "
            "VALUES (?, ?, ?, 'embed', ?, ?, ?)",
            (title, description, category, embed_url.strip(),
             parsed.get("thumbnail"), submitter),
        )
        db.commit()
        db.close()
        return templates.TemplateResponse("submit.html", {
            "request": request,
            "categories": CATEGORIES,
            "error": None,
            "success": True,
        })

    # ── File upload path ────────────────────────────────────────────────────
    if video_file and video_file.filename:
        ext = os.path.splitext(video_file.filename)[1].lower()
        if ext not in ALLOWED_EXTS:
            return templates.TemplateResponse("submit.html", {
                "request": request,
                "categories": CATEGORIES,
                "error": f"File type not allowed. Use: {', '.join(ALLOWED_EXTS)}",
            })

        uid = uuid.uuid4().hex
        filename = f"{uid}{ext}"
        dest = os.path.join(UPLOAD_DIR, filename)

        size = 0
        with open(dest, "wb") as out:
            while chunk := await video_file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    out.close()
                    os.remove(dest)
                    return templates.TemplateResponse("submit.html", {
                        "request": request,
                        "categories": CATEGORIES,
                        "error": f"File too large. Max {MAX_UPLOAD_MB} MB.",
                    })
                out.write(chunk)

        thumbnail = _make_thumbnail(dest, f"{uid}.jpg")

        db = get_db()
        db.execute(
            "INSERT INTO videos (title, description, category, type, file_path, thumbnail, submitter) "
            "VALUES (?, ?, ?, 'upload', ?, ?, ?)",
            (title, description, category, f"/static/uploads/{filename}", thumbnail, submitter),
        )
        db.commit()
        db.close()
        return templates.TemplateResponse("submit.html", {
            "request": request,
            "categories": CATEGORIES,
            "error": None,
            "success": True,
        })

    return templates.TemplateResponse(request, "submit.html", {
        "categories": CATEGORIES,
        "error": "Please paste a URL or choose a file to upload.",
    })
