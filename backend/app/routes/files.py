import os
import shutil
import tempfile
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from fastapi.responses import StreamingResponse
import urllib.parse

from app.database import get_db
from app.models import User, FileRecord
from app.auth import get_current_user
from app.schemas import FileOut, Message
from app.services.telegram_service import upload_file_to_telegram, download_file_stream, delete_file_from_telegram

router = APIRouter()

@router.post("/api/upload", response_model=FileOut)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.telegram_session or not current_user.channel_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram account not connected.")

    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    try:
        MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
        
        # FastAPI's UploadFile may populate the size attribute
        if file.size and file.size > MAX_SIZE:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds the 2GB limit.")

        file_size = 0
        with open(temp_file_path, "wb") as buffer:
            while chunk := file.file.read(8192 * 4):  # 32KB chunks
                file_size += len(chunk)
                if file_size > MAX_SIZE:
                    buffer.close()
                    os.remove(temp_file_path)
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds the 2GB limit.")
                buffer.write(chunk)
        
        msg_id = await upload_file_to_telegram(
            session_string=current_user.telegram_session,
            channel_id=current_user.channel_id,
            file_path=temp_file_path,
            filename=file.filename
        )
        
        file_record = FileRecord(
            user_id=current_user.id,
            original_name=file.filename,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            telegram_message_id=msg_id
        )
        
        db.add(file_record)
        db.commit()
        db.refresh(file_record)
        
        return file_record
        
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload file: {str(e)}")
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

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
        stream = download_file_stream(
            session_string=current_user.telegram_session,
            channel_id=current_user.channel_id,
            message_id=file_record.telegram_message_id
        )
        
        safe_filename = urllib.parse.quote(file_record.original_name)
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}"
        }
        
        return StreamingResponse(stream, media_type=file_record.mime_type, headers=headers)
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
        await delete_file_from_telegram(
            session_string=current_user.telegram_session,
            channel_id=current_user.channel_id,
            message_id=file_record.telegram_message_id
        )
        
        db.delete(file_record)
        db.commit()
        return Message(message="File deleted successfully.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete file: {str(e)}")
