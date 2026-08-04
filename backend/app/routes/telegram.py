from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import get_current_user
from app.schemas import TelegramQRStartResponse, TelegramQRStatusResponse, Message
from app.services.telegram_service import start_qr_login, check_qr_login_status

router = APIRouter()

@router.post("/api/telegram/qr-start", response_model=TelegramQRStartResponse)
async def api_qr_start(current_user: User = Depends(get_current_user)):
    try:
        token_id, url = await start_qr_login()
        return TelegramQRStartResponse(token=token_id, url=url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to start QR login: {str(e)}"
        )

@router.get("/api/telegram/qr-status", response_model=TelegramQRStatusResponse)
async def api_qr_status(token: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    info = check_qr_login_status(token)
    
    if info["status"] == "success":
        try:
            # Save to database
            from app.auth import encrypt_telegram_session
            current_user.telegram_session = encrypt_telegram_session(info["session_string"])
            current_user.telegram_user_id = info["tg_user_id"]
            current_user.channel_id = info["channel_id"]
            
            db.commit()
            
            return TelegramQRStatusResponse(status="success", message="Telegram account connected and private channel created successfully.")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save session to DB: {str(e)}"
            )
            
    return TelegramQRStatusResponse(status=info["status"])
