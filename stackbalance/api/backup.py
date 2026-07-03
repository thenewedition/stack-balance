"""One-click portable backup and restore."""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from .. import config, schemas
from ..services import backup as backup_service
from .deps import get_session

router = APIRouter()


@router.post("/backups", response_model=schemas.BackupOut, status_code=201)
def create_backup(session: Session = Depends(get_session)):
    filename, payload = backup_service.create_backup(session)
    return schemas.BackupOut(
        filename=filename,
        size_bytes=len(payload),
        created_at=datetime.fromtimestamp((config.backups_dir() / filename).stat().st_mtime),
    )


@router.get("/backups", response_model=list[schemas.BackupOut])
def list_backups():
    return [schemas.BackupOut(**b) for b in backup_service.list_backups()]


@router.get("/backups/{filename}")
def download_backup(filename: str):
    path = (config.backups_dir() / filename).resolve()
    if path.parent != config.backups_dir().resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="backup not found")
    return FileResponse(path, media_type="application/zip", filename=filename)


@router.delete("/backups/{filename}", status_code=204)
def delete_backup(filename: str):
    path = (config.backups_dir() / filename).resolve()
    if path.parent != config.backups_dir().resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="backup not found")
    path.unlink()
    return Response(status_code=204)


@router.post("/backups/restore", response_model=schemas.RestoreResult)
async def restore_backup(file: UploadFile = File(...), session: Session = Depends(get_session)):
    content = await file.read()
    try:
        counts = backup_service.restore_backup(session, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return schemas.RestoreResult(restored=True, counts=counts)
