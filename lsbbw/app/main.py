from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from app.database import init_db
from app.routes import videos, submit, admin, account, billing, agegate

_AGE_GATE_EXEMPT = ("/static", "/age-gate", "/favicon.ico", "/robots.txt")


class AgeGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if not any(path.startswith(p) for p in _AGE_GATE_EXEMPT):
            if request.cookies.get("age_verified") != "1":
                return RedirectResponse(f"/age-gate?next={path}", status_code=302)
        return await call_next(request)


app = FastAPI(title="LSBBW", docs_url=None, redoc_url=None)
app.add_middleware(AgeGateMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(agegate.router)
app.include_router(videos.router)
app.include_router(submit.router)
app.include_router(admin.router)
app.include_router(account.router)
app.include_router(billing.router)


@app.on_event("startup")
async def startup():
    init_db()
