from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import get_current_user
from app.schemas import TelegramQRStartResponse, TelegramQRStatusResponse, Message, Telegram2FARequest, TelegramMismatchOverrideRequest
from app.services.telegram_service import start_qr_login, check_qr_login_status, submit_qr_password, override_account_mismatch

router = APIRouter()

@router.post("/api/telegram/2fa", response_model=TelegramQRStatusResponse)
async def api_submit_2fa(req: Telegram2FARequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        info = await submit_qr_password(req.token, req.password, force_new_channel=req.force_new_channel)
        if info["status"] == "success":
            from app.auth import encrypt_telegram_session
            current_user.telegram_session = encrypt_telegram_session(info["session_string"])
            current_user.telegram_user_id = info["tg_user_id"]
            current_user.channel_id = info["channel_id"]
            db.commit()
            return TelegramQRStatusResponse(status="success", message="2FA successful. Telegram account connected and private channel created.")
        elif info["status"] == "account_mismatch":
            return TelegramQRStatusResponse(status="account_mismatch", message="This is a different Telegram account than before.")
        elif info["status"] == "failed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to verify 2FA password: {info.get('error', 'Unknown error')}"
            )
        else:
            return TelegramQRStatusResponse(status=info["status"], message="Invalid state or token.")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit 2FA: {str(e)}"
        )

@router.post("/api/telegram/qr-start", response_model=TelegramQRStartResponse)
async def api_qr_start(current_user: User = Depends(get_current_user)):
    try:
        token_id, url = await start_qr_login(
            user_channel_id=current_user.channel_id,
            user_tg_user_id=current_user.telegram_user_id
        )
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
    elif info["status"] == "account_mismatch":
        return TelegramQRStatusResponse(status="account_mismatch", message="This is a different Telegram account than before.")
            
    return TelegramQRStatusResponse(status=info["status"])

@router.post("/api/telegram/override-mismatch", response_model=TelegramQRStatusResponse)
async def api_override_mismatch(req: TelegramMismatchOverrideRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    info = await override_account_mismatch(req.token)
    if info["status"] == "success":
        info2 = check_qr_login_status(req.token) # This gets the full details and deletes from pending
        if info2["status"] == "success":
            try:
                from app.auth import encrypt_telegram_session
                current_user.telegram_session = encrypt_telegram_session(info2["session_string"])
                current_user.telegram_user_id = info2["tg_user_id"]
                current_user.channel_id = info2["channel_id"]
                db.commit()
                return TelegramQRStatusResponse(status="success", message="Mismatched account accepted. New private channel created.")
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save session to DB: {str(e)}")
    raise HTTPException(status_code=400, detail="Invalid token or state")

@router.post("/api/telegram/disconnect")
async def api_telegram_disconnect(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.telegram_session = None
    current_user.telegram_user_id = None
    db.commit()
    return {"status": "success", "message": "Telegram disconnected"}
