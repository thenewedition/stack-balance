from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from . import __version__
from .api import backup, budget, core, importer, recurring, reports, sinking, transactions
from .database import init_db

STATIC_DIR = Path(__file__).parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stack Balance",
        description="Self-hosted, local-first zero-based budgeting",
        version=__version__,
        lifespan=lifespan,
    )

    for router in (core.router, transactions.router, budget.router, recurring.router,
                   sinking.router, importer.router, backup.router, reports.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
