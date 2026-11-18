from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.note import Note
from app.models.user import User
from app.schemas.note import NoteCreate, NoteDetail, NoteSummary

router = APIRouter(prefix="/notes", tags=["Notes"])


@router.get("", response_model=list[NoteSummary])
def list_notes(
    topic: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Note).order_by(Note.id)
    if topic:
        query = query.where(Note.topic == topic)
    return db.scalars(query).all()


@router.get("/{note_id}", response_model=NoteDetail)
def get_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = db.get(Note, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.post("", response_model=NoteDetail, status_code=status.HTTP_201_CREATED)
def create_note(
    data: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("teacher", "admin")),
):
    note = Note(
        title=data.title,
        topic=data.topic,
        body=data.body,
        created_by=current_user.id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
