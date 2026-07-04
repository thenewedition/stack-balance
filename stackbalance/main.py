from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import (autocat, backup, budget, core, importer, recurring, reports,
                  sinking, transactions)
from .database import init_db

STATIC_DIR = Path(__file__).parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Credit accounts created before payment envelopes existed get one now.
    from .database import get_session
    from .services import credit

    session_gen = get_session()
    credit.ensure_all_payment_categories(next(session_gen))
    session_gen.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stack Balance",
        description="Self-hosted, local-first zero-based budgeting",
        version=__version__,
        lifespan=lifespan,
    )

    for router in (core.router, transactions.router, budget.router, recurring.router,
                   sinking.router, importer.router, backup.router, reports.router,
                   autocat.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/", include_in_schema=False)
    def spa():
        return FileResponse(STATIC_DIR / "index.html")

    # PWA files must be served from the root so the service worker can claim
    # scope "/" and the manifest resolves relative to it.
    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(STATIC_DIR / "manifest.webmanifest",
                            media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


app = create_app()
