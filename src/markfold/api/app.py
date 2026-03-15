from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from markfold.api.routes import router as api_router
from markfold.config import get_settings
from markfold.repositories import init_database
from markfold.web.routes import router as web_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)

    @app.on_event("startup")
    def startup() -> None:
        init_database()

    app.include_router(api_router)
    app.include_router(web_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "markfold.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
