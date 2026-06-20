from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/age-gate", response_class=HTMLResponse)
async def age_gate(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "age_gate.html", {"next": next})


@router.post("/age-gate/confirm")
async def age_gate_confirm(request: Request, next: str = Form("/"), confirm: str = Form(...)):
    if confirm == "yes":
        resp = RedirectResponse(next, status_code=302)
        resp.set_cookie("age_verified", "1", max_age=2592000, httponly=True, samesite="lax")
        return resp
    return RedirectResponse("https://www.google.com", status_code=302)
