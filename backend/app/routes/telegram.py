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
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

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
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to submit 2FA for token %s", req.token)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during 2FA verification.",
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
    except Exception:
        logger.exception("Failed to start phone login for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to send verification code. Please try again.",
        )

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
    except Exception:
        logger.exception("Error submitting phone code for token %s", req.token)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while verifying the code.",
        )

@router.post("/api/telegram/qr-start", response_model=TelegramQRStartResponse)
async def api_qr_start(current_user: User = Depends(get_current_user)):
    try:
        token_id, url = await start_qr_login(
            user_channel_id=current_user.channel_id,
            user_tg_user_id=current_user.telegram_user_id
        )
        return TelegramQRStartResponse(token=token_id, url=url)
    except Exception:
        logger.exception("Failed to start QR login for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to start QR login. Please try again.",
        )

@router.get("/api/telegram/qr-status", response_model=TelegramQRStatusResponse)
async def api_qr_status(token: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    info = check_qr_login_status(token)
    
    if info["status"] == "success":
        try:
            # Save to database
            _save_telegram_session(current_user, info, db)
            
            return TelegramQRStatusResponse(status="success", message="Telegram account connected and private channel created successfully.")
        except Exception:
            logger.exception("Failed to save Telegram session for user %s", current_user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Connected to Telegram but failed to save the session. Please try again.",
            )
    elif info["status"] == "account_mismatch":
        return TelegramQRStatusResponse(status="account_mismatch", message="This is a different Telegram account than before.")
            
    return TelegramQRStatusResponse(status=info["status"])

@router.post("/api/telegram/override-mismatch", response_model=TelegramQRStatusResponse)
async def api_override_mismatch(req: TelegramMismatchOverrideRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        info = await override_account_mismatch(req.token)
        if info["status"] == "success":
            info2 = check_qr_login_status(req.token) # This gets the full details and deletes from pending
            if info2["status"] == "success":
                try:
                    _save_telegram_session(current_user, info2, db)
                    return TelegramQRStatusResponse(status="success", message="Mismatched account accepted. New private channel created.")
                except Exception:
                    logger.exception("Failed to save session during mismatch override for user %s", current_user.id)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Connected but failed to save the session. Please try again.",
                    )
        raise HTTPException(status_code=400, detail="Invalid token or state")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error overriding mismatch for token %s", req.token)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to override account mismatch. Please try again.",
        )

@router.post("/api/telegram/disconnect")
async def api_telegram_disconnect(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.services.telegram_service import _client_cache
    old_session = current_user.telegram_session
    current_user.telegram_session = None
    current_user.telegram_user_id = None
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to clear telegram session in database for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect Telegram account. Please try again.",
        )
    if old_session and old_session in _client_cache:
        client = _client_cache.pop(old_session)
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            logger.warning("Failed to cleanly disconnect cached client during disconnect")
    return {"status": "success", "message": "Telegram disconnected"}
