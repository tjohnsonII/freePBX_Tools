from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import init_db
from app.routes import videos, submit, admin, account

app = FastAPI(title="LSBBW", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(videos.router)
app.include_router(submit.router)
app.include_router(admin.router)
app.include_router(account.router)


@app.on_event("startup")
async def startup():
    init_db()
