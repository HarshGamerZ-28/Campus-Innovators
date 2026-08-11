from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..activity import record_activity
from ..daily_quests import record_daily_quest_progress
from ..database import get_db
from ..deps import get_current_user
from ..models import Event, EventRegistration, User
from ..schemas import EventCreate
from ..serializers import event_public

router = APIRouter(prefix="/events", tags=["Events"])


def event_query():
    return select(Event).options(selectinload(Event.organizer), selectinload(Event.registrations))


@router.get("")
def list_events(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    events = db.scalars(event_query().order_by(Event.event_date)).all()
    return [event_public(event, current_user.id) for event in events]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    event = Event(
        title=payload.title.strip(),
        description=payload.description.strip(),
        venue=payload.venue.strip(),
        event_date=payload.event_date,
        capacity=payload.capacity,
        organizer_id=current_user.id,
    )
    db.add(event)
    record_activity(db, current_user.id, 2)
    db.commit()
    event = db.scalar(event_query().where(Event.id == event.id))
    return event_public(event, current_user.id)


@router.post("/{event_id}/register")
def toggle_registration(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    event = db.scalar(event_query().where(Event.id == event_id))
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    registration = next((item for item in event.registrations if item.user_id == current_user.id), None)
    if registration:
        db.delete(registration)
        registered = False
    else:
        if len(event.registrations) >= event.capacity:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Event is full")
        db.add(EventRegistration(event_id=event_id, user_id=current_user.id))
        registered = True
        record_activity(db, current_user.id)
        record_daily_quest_progress(db, current_user, "register_event")
    db.commit()
    event = db.scalar(event_query().where(Event.id == event_id))
    return {"registered": registered, "registered_count": len(event.registrations)}
