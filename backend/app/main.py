import logging
import time
import uuid

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health, invoices, suppliers
from app.core.config import get_settings
from app.core.errors import register_error_handlers

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("blinkhub")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="0.1.0",
        description="Procure-to-pay visibility, invoice tracking and risk flags for BlinkHub. "
        "Demonstration data only.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        rid = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = rid
        log.info(
            "rid=%s %s %s %s %.1fms",
            rid,
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
        return response

    register_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth.router)
    api.include_router(suppliers.router)
    api.include_router(invoices.router)
    app.include_router(health.router)
    app.include_router(api)
    return app


app = create_app()
