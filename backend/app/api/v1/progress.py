from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.progress import ProgressOut
from app.services.progress_service import get_progress

router = APIRouter(prefix="/progress", tags=["Progress"])


@router.get("/me", response_model=ProgressOut)
def my_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_progress(db, current_user)