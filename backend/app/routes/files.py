import os
import shutil
import tempfile
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from fastapi.responses import StreamingResponse
import urllib.parse

from app.database import get_db
from app.models import User, FileRecord, FilePartRecord
from app.auth import get_current_user
from app.schemas import FileOut, Message
from app.services.telegram_service import (
    upload_file_to_telegram, 
    download_file_stream, 
    delete_file_from_telegram,
    upload_chunk_to_telegram,
    finalize_telegram_upload
)
from pydantic import BaseModel

class ChunkUploadParams(BaseModel):
    file_id: int
    start_part_index: int
    total_parts: int
    is_big: bool

class FinalizeVolumeParams(BaseModel):
    file_id: int
    total_parts: int
    filename: str
    is_big: bool

class CompleteUploadParams(BaseModel):
    filename: str
    file_size: int
    mime_type: str
    message_ids: List[int]

router = APIRouter()

def handle_telegram_error(e: Exception, db: Session, current_user: User):
    error_name = type(e).__name__
    expired_errors = [
        "AuthKeyUnregisteredError", "SessionExpiredError", "SessionRevokedError", 
        "UserDeactivatedError", "UserDeactivatedBanError", "UnauthorizedError"
    ]
    if any(err in error_name for err in expired_errors):
        current_user.telegram_session = None
        current_user.channel_id = None
        current_user.is_telegram_connected = False
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Telegram session expired or revoked. Please reconnect your account."
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        detail=f"Telegram operation failed: {str(e)}"
    )

@router.post("/api/upload/chunk")
async def upload_chunk(
    file_id: int = Form(...),
    start_part_index: int = Form(...),
    total_parts: int = Form(...),
    is_big: bool = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.telegram_session or not current_user.channel_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram account not connected.")

    try:
        chunk_data = await file.read()
        await upload_chunk_to_telegram(
            session_string=current_user.telegram_session,
            file_id=file_id,
            start_part_index=start_part_index,
            total_parts=total_parts,
            chunk_data=chunk_data,
            is_big=is_big
        )
        return {"status": "success"}
    except Exception as e:
        handle_telegram_error(e, db, current_user)

@router.post("/api/upload/finalize_volume")
async def finalize_volume(
    params: FinalizeVolumeParams,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.telegram_session or not current_user.channel_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram account not connected.")

    try:
        msg_id = await finalize_telegram_upload(
            session_string=current_user.telegram_session,
            channel_id=current_user.channel_id,
            file_id=params.file_id,
            total_parts=params.total_parts,
            filename=params.filename,
            is_big=params.is_big
        )
        return {"message_id": msg_id}
    except Exception as e:
        handle_telegram_error(e, db, current_user)

@router.post("/api/upload/complete", response_model=FileOut)
def complete_upload(
    params: CompleteUploadParams,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        file_record = FileRecord(
            user_id=current_user.id,
            original_name=params.filename,
            file_size=params.file_size,
            mime_type=params.mime_type or "application/octet-stream"
        )
        db.add(file_record)
        db.commit()
        db.refresh(file_record)
        
        for idx, msg_id in enumerate(params.message_ids):
            part_record = FilePartRecord(
                file_id=file_record.id,
                part_index=idx,
                telegram_message_id=msg_id
            )
            db.add(part_record)
            
        db.commit()
        db.refresh(file_record)
        return file_record
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to complete upload: {str(e)}")

@router.get("/api/files", response_model=List[FileOut])
def get_files(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Retrieve all files for the current user."""
    files = db.query(FileRecord).filter(FileRecord.user_id == current_user.id).order_by(FileRecord.uploaded_at.desc()).all()
    return files

@router.get("/api/download/{file_id}")
async def download_file(
    file_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Streams a file directly from Telegram."""
    if not current_user.telegram_session or not current_user.channel_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram account not connected.")
        
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        
    try:
        async def combined_stream():
            parts = sorted(file_record.parts, key=lambda p: p.part_index)
            for part in parts:
                stream = download_file_stream(
                    session_string=current_user.telegram_session,
                    channel_id=current_user.channel_id,
                    message_id=part.telegram_message_id
                )
                async for chunk in stream:
                    yield chunk

        safe_filename = urllib.parse.quote(file_record.original_name)
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}"
        }
        
        return StreamingResponse(combined_stream(), media_type=file_record.mime_type, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to stream file: {str(e)}")

@router.delete("/api/files/{file_id}", response_model=Message)
async def delete_file(
    file_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """Deletes a file from Telegram and the local database."""
    if not current_user.telegram_session or not current_user.channel_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram account not connected.")
        
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        
    try:
        for part in file_record.parts:
            await delete_file_from_telegram(
                session_string=current_user.telegram_session,
                channel_id=current_user.channel_id,
                message_id=part.telegram_message_id
            )
        
        db.delete(file_record)
        db.commit()
        return Message(message="File deleted successfully.")
    except Exception as e:
        handle_telegram_error(e, db, current_user)
