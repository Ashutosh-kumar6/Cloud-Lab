from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.recommendation import RecommendationsOut
from app.services.recommendation_service import get_recommendations

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/me", response_model=RecommendationsOut)
def my_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_recommendations(db, current_user)
