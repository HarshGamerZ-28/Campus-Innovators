from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..activity import record_activity
from ..daily_quests import record_daily_quest_progress
from ..database import get_db
from ..deps import get_current_user
from ..models import Event, EventRegistration, Meeting, MeetingAttendance, User
from ..notify import notify_active_users
from ..schemas import EventCreate, UnifiedEventOut
from ..serializers import event_public

router = APIRouter(prefix="/events", tags=["Events"])


def event_query():
    return select(Event).options(selectinload(Event.organizer), selectinload(Event.registrations))


@router.get("", response_model=list[UnifiedEventOut])
def list_events(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    """Unified public feed: real Event rows + Meeting rows that opted in via
    visible_on_events, normalized to UnifiedEventOut and sorted by date.

    Read-time merge only — Meeting stays the single source of truth for
    meeting data, nothing is copied into the events table.
    """
    events = db.scalars(event_query().order_by(Event.event_date)).all()
    event_items = [
        {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "date": event.event_date,
            "location": event.venue,
            "source": "event",
            "created_by": event.organizer.name,
            "capacity": event.capacity,
            "registered_count": len(event.registrations),
            "registered": any(item.user_id == current_user.id for item in event.registrations),
            "attendee_count": None,
        }
        for event in events
    ]

    meetings = list(
        db.scalars(
            select(Meeting)
            .options(selectinload(Meeting.created_by))
            .where(Meeting.visible_on_events.is_(True))
        ).all()
    )
    attendee_counts = dict(
        db.execute(
            select(MeetingAttendance.meeting_id, func.count(MeetingAttendance.id)).group_by(MeetingAttendance.meeting_id)
        ).all()
    )
    meeting_items = [
        {
            "id": meeting.id,
            "title": meeting.title,
            "description": meeting.description,
            "date": meeting.scheduled_at,
            "location": meeting.location,
            "source": "meeting",
            "created_by": meeting.created_by.name,
            "capacity": None,
            "registered_count": None,
            "registered": None,
            "attendee_count": attendee_counts.get(meeting.id, 0),
        }
        for meeting in meetings
    ]

    return sorted(event_items + meeting_items, key=lambda item: item["date"])


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
    notify_active_users(db, message=f'New event: "{event.title}"', kind="event_created", exclude_user_id=current_user.id)
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
