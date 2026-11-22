from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Liveness + database readiness, used by Docker and load-balancer health checks."""
    try:
        db.execute(text("select 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)
