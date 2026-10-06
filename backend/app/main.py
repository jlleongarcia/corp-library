import logging

from fastapi import FastAPI
from sqlalchemy import text

from .config import settings
from .database import engine
from .routers import admin, auth, reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)

# The schema is managed by Alembic (`alembic upgrade head`, run by the container
# entrypoint), never by create_all.
app = FastAPI(
    title=settings.app_name,
    description="Department document library: discovery reports (phase 0).",
    version="0.2.0",
)

# The UI is served by nginx on the same origin and proxies /api, so no CORS is needed.
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(reports.router)


@app.get("/health", tags=["system"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "app": settings.app_name}
