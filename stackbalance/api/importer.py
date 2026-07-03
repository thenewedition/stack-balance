"""Universal CSV/JSON import endpoint."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..services import importer as importer_service
from .deps import get_session

router = APIRouter()


@router.post("/import", response_model=schemas.ImportResult)
async def import_file(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    skip_duplicates: bool = Form(True),
    column_mapping: str | None = Form(None, description='Optional JSON, e.g. {"date": "Posted"}'),
    session: Session = Depends(get_session),
):
    if session.get(models.Account, account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    mapping = None
    if column_mapping:
        try:
            mapping = json.loads(column_mapping)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="column_mapping must be valid JSON")
    content = await file.read()
    try:
        return importer_service.import_rows(
            session,
            account_id=account_id,
            content=content,
            filename=file.filename or "",
            dry_run=dry_run,
            skip_duplicates=skip_duplicates,
            column_mapping=mapping,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
