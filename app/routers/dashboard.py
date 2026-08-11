from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dashboard_data import build_dashboard
from ..database import get_db
from ..deps import get_current_user
from ..models import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("")
def dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return build_dashboard(db, current_user, private=True)
