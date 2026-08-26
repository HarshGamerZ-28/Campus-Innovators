from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import Notification, Opportunity, User
from ..schemas import OpportunityCreate, OpportunityOut, OpportunityReview, OpportunityUpdate

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


def _is_admin(user: User) -> bool:
    return user.role.lower() in {"admin", "founder"}


def _get_opportunity(db: Session, opportunity_id: int) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    return opportunity


def _require_owner_while_pending_or_admin(opportunity: Opportunity, user: User) -> None:
    """Edits/deletes are allowed for the submitter only while their post is still
    pending review, or for an admin at any time — matching the spec's "owner (if
    pending) or admin" rule so an approved/rejected listing can't be silently
    altered by its original submitter after the fact."""
    if _is_admin(user):
        return
    if opportunity.submitted_by != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot modify another member's submission")
    if opportunity.status != "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only pending submissions can be edited")


# NOTE: static-path routes ("/mine", "/pending") are declared before the
# "/{opportunity_id}" dynamic route below so FastAPI doesn't try to parse
# "mine"/"pending" as an opportunity_id.


@router.get("/mine", response_model=list[OpportunityOut])
def list_my_opportunities(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Opportunity]:
    return list(
        db.scalars(
            select(Opportunity).where(Opportunity.submitted_by == current_user.id).order_by(Opportunity.created_at.desc())
        ).all()
    )


@router.get("/pending", response_model=list[OpportunityOut])
def list_pending_opportunities(current_user: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[Opportunity]:
    return list(
        db.scalars(
            select(Opportunity).where(Opportunity.status == "pending").order_by(Opportunity.created_at.asc())
        ).all()
    )


@router.post("", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Opportunity:
    opportunity = Opportunity(
        submitted_by=current_user.id,
        # Admins/founders post directly to the live board; everyone else's
        # submission waits for review (see spec).
        status="approved" if _is_admin(current_user) else "pending",
        **payload.model_dump(),
    )
    db.add(opportunity)
    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(
    type: str | None = None,
    location: str | None = None,
    include_expired: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[Opportunity]:
    query = select(Opportunity).where(Opportunity.status == "approved")
    if type:
        query = query.where(Opportunity.type == type)
    if location:
        query = query.where(Opportunity.location == location)
    if not include_expired:
        today = date.today()
        # Opportunities with no deadline never expire, so keep those alongside
        # ones whose deadline hasn't passed yet.
        query = query.where((Opportunity.deadline.is_(None)) | (Opportunity.deadline >= today))
    query = query.order_by(Opportunity.deadline.is_(None), Opportunity.deadline.asc())
    return list(db.scalars(query).all())


@router.get("/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)) -> Opportunity:
    return _get_opportunity(db, opportunity_id)


@router.put("/{opportunity_id}", response_model=OpportunityOut)
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Opportunity:
    opportunity = _get_opportunity(db, opportunity_id)
    _require_owner_while_pending_or_admin(opportunity, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(opportunity, field, value)
    db.commit()
    db.refresh(opportunity)
    return opportunity


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    opportunity = _get_opportunity(db, opportunity_id)
    _require_owner_while_pending_or_admin(opportunity, current_user)
    db.delete(opportunity)
    db.commit()


@router.patch("/{opportunity_id}/review", response_model=OpportunityOut)
def review_opportunity(
    opportunity_id: int,
    payload: OpportunityReview,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Opportunity:
    opportunity = _get_opportunity(db, opportunity_id)
    if payload.action == "approve":
        opportunity.status = "approved"
        opportunity.rejection_reason = None
        db.add(Notification(
            user_id=opportunity.submitted_by,
            message=f'Your opportunity "{opportunity.title}" was approved and is now live.',
            kind="opportunity_approved",
        ))
    else:
        opportunity.status = "rejected"
        opportunity.rejection_reason = (payload.rejection_reason or "").strip() or None
        db.add(Notification(
            user_id=opportunity.submitted_by,
            message=f'Your opportunity "{opportunity.title}" was rejected.',
            kind="opportunity_rejected",
        ))
    opportunity.reviewed_by = current_user.id
    db.commit()
    db.refresh(opportunity)
    return opportunity
