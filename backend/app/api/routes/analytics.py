from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import internal_only
from app.db.session import get_db
from app.models import User
from app.services.analytics import DataSource, overview

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def get_overview(
    data_source: DataSource = "CASE_STUDY", db: Session = Depends(get_db), _: User = Depends(internal_only)
):
    """Dashboard figures. CASE_STUDY = the brief's sample data; SYNTHETIC = demonstration year."""
    return overview(db, data_source)
