"""
Email notification endpoints.
Manages sending transaction review emails and processing replies.
"""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import NotificationLog, Transaction

router = APIRouter()


class NotificationSettings(BaseModel):
    email_enabled: bool = False
    email_address: Optional[str] = None
    batch_interval_minutes: int = 30  # Batch notifications every N minutes
    auto_confirm_threshold: int = 3   # Merchant mapping confidence threshold


@router.get("/settings")
def get_notification_settings():
    """Get current notification settings."""
    # TODO: Read from a settings table or .env
    return NotificationSettings()


@router.post("/settings")
def update_notification_settings(settings: NotificationSettings):
    """Update notification settings."""
    # TODO: Persist to settings table
    return {"status": "updated"}


@router.get("/log")
def get_notification_log(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Get recent notification history."""
    logs = (
        db.query(NotificationLog)
        .order_by(NotificationLog.sent_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "transaction_id": log.transaction_id,
            "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            "replied_at": log.replied_at.isoformat() if log.replied_at else None,
            "reply_category": log.reply_category,
        }
        for log in logs
    ]


@router.post("/test")
def send_test_notification():
    """Send a test email to verify configuration."""
    # TODO: Implement with email_service
    return {"status": "not_implemented", "message": "Email service will be implemented in Phase 3"}
