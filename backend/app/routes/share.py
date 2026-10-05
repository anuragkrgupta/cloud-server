import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, FileRecord, FilePartRecord
from app.auth import get_current_user
from app.schemas import FileOut, Message
from pydantic import BaseModel
from typing import Optional
from app.services.transfer import transfer_file_between_users
import asyncio

router = APIRouter()

class ShareResponse(BaseModel):
    share_token: str
    url: str

@router.post("/api/files/{file_id}/share", response_model=ShareResponse)
def share_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
        
    if not file_record.share_token:
        file_record.share_token = str(uuid.uuid4())
        file_record.is_shared = True
        db.commit()
        db.refresh(file_record)
        
    return {"share_token": file_record.share_token, "url": f"/share.html?token={file_record.share_token}"}

@router.post("/api/files/{file_id}/unshare", response_model=Message)
def unshare_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.user_id == current_user.id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_record.share_token = None
    file_record.is_shared = False
    db.commit()
    
    return {"message": "File is no longer shared."}


class SharedFileInfo(BaseModel):
    original_name: str
    file_size: int
    owner_name: str
    
@router.get("/api/shared/{token}", response_model=SharedFileInfo)
def get_shared_file_info(token: str, db: Session = Depends(get_db)):
    file_record = db.query(FileRecord).filter(FileRecord.share_token == token, FileRecord.is_shared == True).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="Shared file not found or link has expired.")
        
    return {
        "original_name": file_record.original_name,
        "file_size": file_record.file_size,
        "owner_name": file_record.user.name
    }

from fastapi.responses import StreamingResponse
import urllib.parse
from app.services.telegram_service import download_multiple_messages_stream

@router.get("/api/shared/{token}/download")
async def download_shared_file(token: str, db: Session = Depends(get_db)):
    file_record = db.query(FileRecord).filter(FileRecord.share_token == token, FileRecord.is_shared == True).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="Shared file not found or link has expired.")
        
    owner = file_record.user
    if not owner.telegram_session or not owner.channel_id:
        raise HTTPException(status_code=400, detail="Owner's Telegram account is not connected.")
        
    try:
        parts = sorted(file_record.parts, key=lambda p: p.part_index)
        message_ids = [part.telegram_message_id for part in parts]
        channel_id = parts[0].channel_id if (len(parts) > 0 and parts[0].channel_id) else owner.channel_id
        
        stream = await download_multiple_messages_stream(
            session_string=owner.telegram_session,
            channel_id=channel_id,
            message_ids=message_ids
        )
        
        safe_filename = urllib.parse.quote(file_record.original_name)
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
            "Content-Length": str(file_record.file_size),
        }
        
        return StreamingResponse(stream, media_type=file_record.mime_type, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream file: {str(e)}")

@router.post("/api/shared/{token}/save")
async def save_shared_file(
    token: str, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Saves a shared file to the current user's cloud storage.
    Initiates an asynchronous background transfer.
    """
    if not current_user.is_telegram_connected:
        raise HTTPException(status_code=400, detail="You must connect your Telegram account first.")
        
    source_file = db.query(FileRecord).filter(FileRecord.share_token == token, FileRecord.is_shared == True).first()
    if not source_file:
        raise HTTPException(status_code=404, detail="Shared file not found.")
        
    if source_file.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="This is already your file.")

    owner = source_file.user
    if not owner.is_telegram_connected:
        raise HTTPException(status_code=400, detail="The owner's Telegram account is currently disconnected. Cannot transfer file.")
        
    # Get message ids of the source file
    message_ids = [part.telegram_message_id for part in sorted(source_file.parts, key=lambda p: p.part_index)]
    
    asyncio.create_task(
        transfer_file_between_users(
            source_user_id=owner.id,
            target_user_id=current_user.id,
            source_file_id=source_file.id,
            message_ids=message_ids
        )
    )
    
    return {"message": "Transfer started in the background. It will appear in your dashboard soon."}
