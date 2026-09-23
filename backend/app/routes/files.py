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
    download_file_stream, 
    download_multiple_messages_stream,
    delete_file_from_telegram,
)
from pydantic import BaseModel

router = APIRouter()

from telethon.errors import SessionExpiredError, AuthKeyUnregisteredError

def handle_telegram_error(e: Exception, db: Session, current_user: User):
    if isinstance(e, (SessionExpiredError, AuthKeyUnregisteredError)):
        current_user.telegram_session = None
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram session expired or revoked. Please reconnect your account.")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

class CompleteUploadParams(BaseModel):
    filename: str
    file_size: int
    mime_type: str
    message_ids: List[int]

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
                telegram_message_id=msg_id,
                channel_id=current_user.channel_id
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
        # Load parts before returning so we don't hit DetachedInstanceError 
        # when the async generator runs after the db session is closed.
        parts = sorted(file_record.parts, key=lambda p: p.part_index)
        message_ids = [part.telegram_message_id for part in parts]
        
        try:
            channel_id = parts[0].channel_id if (len(parts) > 0 and parts[0].channel_id) else current_user.channel_id
            
            stream = await download_multiple_messages_stream(
                session_string=current_user.telegram_session,
                channel_id=channel_id,
                message_ids=message_ids
            )
        except HTTPException:
            raise
        except Exception as e:
            handle_telegram_error(e, db, current_user)
            raise HTTPException(status_code=500, detail=str(e))

        safe_filename = urllib.parse.quote(file_record.original_name)
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
            "Content-Length": str(file_record.file_size),
        }
        
        return StreamingResponse(stream, media_type=file_record.mime_type, headers=headers)
    except HTTPException:
        raise
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
            channel_id = part.channel_id or current_user.channel_id
            await delete_file_from_telegram(
                session_string=current_user.telegram_session,
                channel_id=channel_id,
                message_id=part.telegram_message_id
            )
        
        db.delete(file_record)
        db.commit()
        return Message(message="File deleted successfully.")
    except Exception as e:
        handle_telegram_error(e, db, current_user)


from fastapi import Request

@router.post("/api/upload/stream")
async def upload_volume_stream(
    request: Request,
    filename: str,
    filesize: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.telegram_session or not current_user.channel_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram account not connected.")
        
    content_length = filesize or request.headers.get("Content-Length")
    if not content_length:
        raise HTTPException(400, "Content-Length header or filesize parameter required")
        
    try:
        from app.services.telegram_service import upload_stream_to_telegram
        message_id = await upload_stream_to_telegram(
            session_string=current_user.telegram_session,
            channel_id=current_user.channel_id,
            filename=filename,
            file_size=int(content_length),
            stream=request.stream()
        )
        return {"status": "success", "message_id": message_id}
    except Exception as e:
        handle_telegram_error(e, db, current_user)
