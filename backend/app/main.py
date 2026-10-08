import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import dev_mode_problem, settings
from .database import engine
from .routers import admin, auth, library, plan, privacy, reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)

# Dev sign-in takes no password: refuse to start anywhere it could be reached
# by real users (BUG-017).
if settings.dev_mode and (problem := dev_mode_problem(settings)):
    raise RuntimeError(problem)

# The schema is managed by Alembic (`alembic upgrade head`, run by the container
# entrypoint), never by create_all.
app = FastAPI(
    title=settings.app_name,
    description="Department document library: search and browse the shares with Windows permissions.",
    version="0.4.0",
)

# The UI is served by nginx on the same origin and proxies /api, so no CORS is needed.
app.include_router(auth.router)
app.include_router(library.router)
app.include_router(admin.router)
app.include_router(reports.router)
app.include_router(plan.router)
app.include_router(plan.admin)
app.include_router(privacy.router)

if not settings.dev_mode and (missing := privacy.missing_settings()):
    # Not fatal (the app works), but the privacy notice is incomplete without them (BUG-033).
    logging.getLogger(__name__).warning("Privacy notice incomplete: set %s in .env.", ", ".join(missing))


@app.exception_handler(StarletteHTTPException)
async def http_errors(request: Request, exc: StarletteHTTPException):
    # Download/preview links opened by the browser get a page, not JSON (BUG-028).
    page = library.error_page(request, exc.status_code, exc.detail)
    return page or await http_exception_handler(request, exc)


@app.get("/health", tags=["system"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "app": settings.app_name}
