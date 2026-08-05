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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload chunk: {str(e)}")

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to finalize volume: {str(e)}")

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
    inline: bool = False,
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
        # Eagerly extract needed fields while DB session is open
        telegram_session = current_user.telegram_session
        channel_id = current_user.channel_id
        part_message_ids = [p.telegram_message_id for p in sorted(file_record.parts, key=lambda p: p.part_index)]

        async def combined_stream():
            for message_id in part_message_ids:
                stream = download_file_stream(
                    session_string=telegram_session,
                    channel_id=channel_id,
                    message_id=message_id
                )
                async for chunk in stream:
                    yield chunk

        safe_filename = urllib.parse.quote(file_record.original_name)
        disposition = "inline" if inline else "attachment"
        headers = {
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{safe_filename}"
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete file: {str(e)}")
