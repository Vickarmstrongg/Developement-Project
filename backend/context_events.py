from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import database
import models
from access.constants import Role
from access.deps import get_current_user, require_roles

require_admin = require_roles(Role.ADMIN)

router = APIRouter(
    prefix="/context-events",
    tags=["Context events"],
    dependencies=[Depends(get_current_user)],
)


class EventIn(BaseModel):
    name: str
    event_type: str
    start_date: date
    end_date: date


def allowed_types(db):
    return sorted({
        t for (t,) in db.query(
            models.ContextualEvent.event_type
        ).distinct()
        if t
    })


def to_dict(e):
    return {
        "event_id": e.event_id,
        "name": e.name,
        "event_type": e.event_type,
        "start_date": e.start_date.isoformat(),
        "start_time": e.start_time.isoformat() if e.start_time else None,
        "end_date": e.end_date.isoformat(),
        "end_time": e.end_time.isoformat() if e.end_time else None,
        "all_day": e.all_day,
        "location": e.location,
        "campus": e.campus,
        "faculty": e.faculty,
        "scope": e.scope,
        "source": e.source,
        "source_organisation": e.source_organisation,
        "source_name": e.source_name,
        "source_file": e.source_file,
        "source_url": e.source_url,
        "source_page": e.source_page,
        "verification_status": e.verification_status,
        "notes": e.notes,
        "created_by_user_id": e.created_by_user_id,
        "updated_at": (
            e.updated_at.isoformat() if e.updated_at else None
        ),
    }


def check_event(body, db):
    name = body.name.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Event name cannot be empty."
        )

    if body.event_type not in allowed_types(db):
        raise HTTPException(
            status_code=422,
            detail="Pick an event type from the list."
        )

    if body.end_date < body.start_date:
        raise HTTPException(
            status_code=422,
            detail="End date cannot be before the start date."
        )

    return name


@router.get("/types")
def list_types(db: Session = Depends(database.get_db)):
    return {"types": allowed_types(db)}


@router.get("")
def list_events(
    year: int = Query(default=None, ge=1, le=9999),
    event_type: str = None,
    db: Session = Depends(database.get_db)
):
    query = db.query(models.ContextualEvent)

    if year:
        query = query.filter(
            models.ContextualEvent.start_date <= date(year, 12, 31),
            models.ContextualEvent.end_date >= date(year, 1, 1),
        )

    if event_type:
        query = query.filter(
            models.ContextualEvent.event_type == event_type
        )

    events = query.order_by(
        models.ContextualEvent.start_date,
        models.ContextualEvent.event_id
    ).all()

    return {
        "count": len(events),
        "events": [to_dict(e) for e in events],
    }


@router.post("", status_code=201)
def create_event(
    body: EventIn,
    db: Session = Depends(database.get_db),
    admin: dict = Depends(require_admin)
):
    name = check_event(body, db)

    event = models.ContextualEvent(
        name=name,
        event_type=body.event_type,
        start_date=body.start_date,
        end_date=body.end_date,
        source="Admin entry",
        created_by_user_id=admin.user_id,
        updated_at=datetime.now(timezone.utc),
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return to_dict(event)


@router.put("/{event_id}")
def update_event(
    event_id: int,
    body: EventIn,
    db: Session = Depends(database.get_db),
    admin: dict = Depends(require_admin)
):
    event = (
        db.query(models.ContextualEvent)
        .filter(models.ContextualEvent.event_id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found."
        )

    event.name = check_event(body, db)
    event.event_type = body.event_type
    event.start_date = body.start_date
    event.end_date = body.end_date
    event.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(event)

    return to_dict(event)


@router.delete("/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(database.get_db),
    admin: dict = Depends(require_admin)
):
    event = (
        db.query(models.ContextualEvent)
        .filter(models.ContextualEvent.event_id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found."
        )

    db.delete(event)
    db.commit()

    return {"deleted": event_id}
