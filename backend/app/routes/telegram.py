from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import get_current_user
from app.schemas import TelegramQRStartResponse, TelegramQRStatusResponse, Message, Telegram2FARequest, TelegramMismatchOverrideRequest, TelegramPhoneStartRequest, TelegramPhoneCodeRequest
from app.services.telegram_service import start_qr_login, check_qr_login_status, submit_qr_password, override_account_mismatch, start_phone_login, submit_phone_code
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

def _save_telegram_session(current_user: User, info: dict, db: Session):
    from app.auth import encrypt_telegram_session
    current_user.telegram_session = encrypt_telegram_session(info["session_string"])
    current_user.telegram_user_id = info["tg_user_id"]
    current_user.channel_id = info["channel_id"]
    db.commit()

@router.post("/api/telegram/2fa", response_model=TelegramQRStatusResponse)
async def api_submit_2fa(req: Telegram2FARequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        info = await submit_qr_password(req.token, req.password, force_new_channel=req.force_new_channel)
        if info["status"] == "success":
            _save_telegram_session(current_user, info, db)
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

@router.post("/api/telegram/phone-start", response_model=TelegramQRStartResponse)
async def api_phone_start(req: TelegramPhoneStartRequest, current_user: User = Depends(get_current_user)):
    try:
        token_id = await start_phone_login(
            phone_number=req.phone_number,
            user_channel_id=current_user.channel_id,
            user_tg_user_id=current_user.telegram_user_id
        )
        return TelegramQRStartResponse(token=token_id, url="")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to send code: {str(e)}")

@router.post("/api/telegram/phone-code", response_model=TelegramQRStatusResponse)
async def api_phone_code(req: TelegramPhoneCodeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        info = await submit_phone_code(req.token, req.phone_code)
        
        if info["status"] == "success":
            _save_telegram_session(current_user, info, db)
            return TelegramQRStatusResponse(status="success", message="Phone login successful.")
        elif info["status"] == "account_mismatch":
            return TelegramQRStatusResponse(status="account_mismatch", message="This is a different Telegram account than before.")
        elif info["status"] == "2fa_required":
            return TelegramQRStatusResponse(status="2fa_required", message="Two-Step Verification required.")
        elif info["status"] == "not_found":
            raise HTTPException(status_code=400, detail="Login session not found or expired. Please request a new code.")
        elif info["status"] == "invalid_state":
            raise HTTPException(status_code=400, detail="Invalid session state. Please request a new code.")
        else:
            raise HTTPException(status_code=400, detail=f"Verification failed: {info.get('error', info['status'])}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting phone code: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error submitting code: {str(e)}")

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
            _save_telegram_session(current_user, info, db)
            
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
                _save_telegram_session(current_user, info2, db)
                return TelegramQRStatusResponse(status="success", message="Mismatched account accepted. New private channel created.")
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save session to DB: {str(e)}")
    raise HTTPException(status_code=400, detail="Invalid token or state")

@router.post("/api/telegram/disconnect")
async def api_telegram_disconnect(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.services.telegram_service import _client_cache
    old_session = current_user.telegram_session
    current_user.telegram_session = None
    current_user.telegram_user_id = None
    db.commit()
    if old_session and old_session in _client_cache:
        client = _client_cache.pop(old_session)
        if client.is_connected():
            await client.disconnect()
    return {"status": "success", "message": "Telegram disconnected"}
