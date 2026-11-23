from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, internal_only, require_roles
from app.db.session import get_db
from app.models import User
from app.services import compliance

router = APIRouter(tags=["compliance"])
reviewer = require_roles(*compliance.REVIEW_ROLES)

DocType = Literal[
    "TAX_CLEARANCE",
    "BBBEE_CERTIFICATE",
    "BBBEE_AFFIDAVIT",
    "CSD_REPORT",
    "CIPC_REGISTRATION",
    "BANK_CONFIRMATION",
    "COID_LETTER",
]


class VerifyIn(BaseModel):
    issue_date: date
    expiry_date: date


class RejectIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


@router.get("/compliance/overview")
def get_overview(db: Session = Depends(get_db), _: User = Depends(internal_only)):
    """Every active or pending supplier's document status, worst first."""
    return compliance.overview(db)


@router.get("/suppliers/{supplier_id}/documents")
def list_documents(supplier_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Requirements and document history. Suppliers can see only their own."""
    return compliance.supplier_documents(db, user, supplier_id)


@router.post("/suppliers/{supplier_id}/documents", status_code=201)
async def upload_document(
    supplier_id: UUID,
    doc_type: DocType = Form(...),
    expiry_date: date | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a PDF/PNG/JPG (max 5 MB). It waits as UPLOADED until procurement verifies it."""
    content = await file.read()
    doc = compliance.upload(
        db, user, supplier_id, doc_type, file.filename or "document", content, expiry_date
    )
    return doc


@router.post("/compliance/documents/{doc_id}/verify")
def verify_document(
    doc_id: UUID, body: VerifyIn, db: Session = Depends(get_db), user: User = Depends(reviewer)
):
    doc = compliance.verify(db, user, doc_id, body.issue_date, body.expiry_date)
    return doc


@router.post("/compliance/documents/{doc_id}/reject")
def reject_document(
    doc_id: UUID, body: RejectIn, db: Session = Depends(get_db), user: User = Depends(reviewer)
):
    doc = compliance.reject(db, user, doc_id, body.reason)
    return doc


@router.get("/compliance/documents/{doc_id}/file")
def download_document(doc_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    path, doc = compliance.document_file(db, user, doc_id)
    return FileResponse(path, media_type=doc.content_type, filename=doc.original_filename)


@router.post("/jobs/compliance-check")
def run_check(
    db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN", "MANAGER", "PROCUREMENT_OFFICER"))
):
    """Run the daily compliance job now (it also runs at 06:00 every day)."""
    result = compliance.run_compliance_check(db)
    return result
