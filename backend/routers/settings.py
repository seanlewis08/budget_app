"""
Settings API — Read/write app configuration (API keys, preferences).

Settings are stored in the app_settings DB table. When reading a value,
the DB is checked first; if no row exists, the corresponding environment
variable (from .env) is used as fallback.

Endpoints:
- GET  /api/settings           — All settings (values masked for secrets)
- POST /api/settings           — Save one or more settings
"""

import os
import logging
from typing import Dict, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSetting

logger = logging.getLogger(__name__)
router = APIRouter()

# Map of setting key → env var name for fallback
SETTING_ENV_MAP = {
    "plaid_client_id": "PLAID_CLIENT_ID",
    "plaid_secret": "PLAID_SECRET",
    "plaid_production_secret": "PLAID_PRODUCTION_SECRET",
    "plaid_env": "PLAID_ENV",
    "plaid_recovery_code": "PLAID_RECOVERY_CODE",
    "plaid_token_encryption_key": "PLAID_TOKEN_ENCRYPTION_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "auto_confirm_threshold": "AUTO_CONFIRM_THRESHOLD",
}

# Keys that should be masked in GET responses
SECRET_KEYS = {
    "plaid_secret", "plaid_production_secret", "plaid_token_encryption_key",
    "anthropic_api_key", "plaid_recovery_code",
}


def get_setting(key: str, db: Session) -> Optional[str]:
    """Get a setting value: DB first, then .env fallback."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row and row.value:
        return row.value
    env_var = SETTING_ENV_MAP.get(key)
    if env_var:
        return os.getenv(env_var)
    return None


def mask_value(key: str, value: Optional[str]) -> str:
    """Mask secret values for display (show last 4 chars)."""
    if not value:
        return ""
    if key in SECRET_KEYS and len(value) > 4:
        return "•" * 12 + value[-4:]
    return value


class SettingsUpdate(BaseModel):
    settings: Dict[str, str]


@router.get("/")
def get_settings(db: Session = Depends(get_db)):
    """Return all settings with secret values masked."""
    result = {}
    for key in SETTING_ENV_MAP:
        raw = get_setting(key, db)
        result[key] = {
            "value": mask_value(key, raw),
            "is_set": bool(raw),
            "source": _get_source(key, db),
        }
    return result


def _get_source(key: str, db: Session) -> str:
    """Where is this setting coming from?"""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row and row.value:
        return "database"
    env_var = SETTING_ENV_MAP.get(key)
    if env_var and os.getenv(env_var):
        return "env"
    return "not_set"


@router.post("/")
def save_settings(req: SettingsUpdate, db: Session = Depends(get_db)):
    """Save one or more settings to the database."""
    updated = []
    for key, value in req.settings.items():
        if key not in SETTING_ENV_MAP:
            continue  # Ignore unknown keys

        # Skip if value is masked (user didn't change it)
        if value.startswith("•"):
            continue

        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row:
            row.value = value
        else:
            row = AppSetting(key=key, value=value)
            db.add(row)
        updated.append(key)

    db.commit()

    # Update environment variables so they take effect immediately
    for key in updated:
        env_var = SETTING_ENV_MAP.get(key)
        if env_var:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            if row and row.value:
                os.environ[env_var] = row.value
                logger.info(f"Setting {key} updated and applied to environment")

    return {"status": "saved", "updated": updated}
