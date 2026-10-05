from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tellspend.api.auth import get_current_user
from tellspend.api.schemas import (
    CounterpartyCreate,
    CounterpartyResponse,
    CounterpartyUpdate,
    MergeContacts,
)
from tellspend.database.connection import get_db
from tellspend.database.models import Counterparty, ExpenseItemOwner, ExpenseParticipant, User
from tellspend.services.contacts import merge_contacts
from tellspend.services.ownership import get_owned_counterparty


router = APIRouter(
    prefix="/counterparties",
    tags=["counterparties"],
)


def same_name(name: str) -> str:
    return " ".join(name.casefold().split())


def refuse_taken_name(db: Session, user: User, name: str, keep_id: int | None = None) -> None:
    """
    Two contacts with one name can never be told apart (the assistant
    would ask "which Parth?" forever), so a name already used is refused.
    """
    for contact in db.scalars(select(Counterparty).where(Counterparty.owner_user_id == user.id)):
        if contact.id != keep_id and same_name(contact.name) == same_name(name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"You already have {contact.name} in People. Use a different name, "
                       "or add a surname to tell them apart.",
            )


@router.post(
    "",
    response_model=CounterpartyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_counterparty(
    counterparty_data: CounterpartyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Add a contact to your address book.

    Parameters:
        counterparty_data: Name, type (person/business/...) and relation.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The new contact (201).
    """
    refuse_taken_name(db, current_user, counterparty_data.name)

    counterparty = Counterparty(
        owner_user_id=current_user.id,
        name=counterparty_data.name,
        counterparty_type=counterparty_data.counterparty_type,
        relation=counterparty_data.relation,
    )

    db.add(counterparty)
    db.commit()
    db.refresh(counterparty)

    return counterparty


@router.get("", response_model=list[CounterpartyResponse])
def list_counterparties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Your contacts, alphabetically, ignoring upper/lower case.

    Parameters:
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The user's contacts.
    """
    return db.scalars(
        select(Counterparty)
        .where(Counterparty.owner_user_id == current_user.id)
        .order_by(func.lower(Counterparty.name), Counterparty.id)
    ).all()


@router.get("/{counterparty_id}", response_model=CounterpartyResponse)
def get_counterparty(
    counterparty_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        One of your contacts.

    Parameters:
        counterparty_id: The contact to return.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The contact, or 404.
    """
    return get_owned_counterparty(db, current_user, counterparty_id)


@router.patch("/{counterparty_id}", response_model=CounterpartyResponse)
def update_counterparty(
    counterparty_id: int,
    counterparty_data: CounterpartyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Change a contact. Only the fields sent are changed.

    Parameters:
        counterparty_id: The contact to change.
        counterparty_data: The fields to change.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The updated contact, or 404.
    """
    counterparty = get_owned_counterparty(db, current_user, counterparty_id)
    changes = counterparty_data.model_dump(exclude_unset=True)

    if changes.get("name"):
        refuse_taken_name(db, current_user, changes["name"], keep_id=counterparty.id)

    # A shop can't owe part of a cost: one who has a share can't become one.
    if changes.get("counterparty_type") == "BUSINESS" and counterparty.counterparty_type != "BUSINESS":
        has_share = db.scalar(
            select(ExpenseParticipant.id).where(ExpenseParticipant.counterparty_id == counterparty.id).limit(1)
        ) or db.scalar(
            select(ExpenseItemOwner.id).where(ExpenseItemOwner.counterparty_id == counterparty.id).limit(1)
        )
        if has_share:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{counterparty.name} has a share of some expenses, and a shop can't. "
                       "Change those expenses first.",
            )

    # exclude_unset: only the fields that were actually in the request.
    for field, value in changes.items():
        setattr(counterparty, field, value)

    db.commit()
    db.refresh(counterparty)

    return counterparty


@router.post("/{counterparty_id}/merge", response_model=CounterpartyResponse)
def merge_counterparty(
    counterparty_id: int,
    body: MergeContacts,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Merge another of your contacts into this one: the same person
        saved under two names ("Aadhya" and "adhya"). Everything recorded
        with the other moves here, and the other is deleted, so balances
        aren't split.

    Parameters:
        counterparty_id: The contact to keep.
        body: The contact to merge into it.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The kept contact; 404 for someone else's contact, 422 for itself.
    """
    target = get_owned_counterparty(db, current_user, counterparty_id)
    source = get_owned_counterparty(db, current_user, body.into_id)
    if source.id == target.id:
        raise HTTPException(status_code=422, detail="A contact can't be merged into itself.")

    kept = merge_contacts(db, current_user, source, target)
    db.commit()
    db.refresh(kept)
    return kept


@router.delete("/{counterparty_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_counterparty(
    counterparty_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Delete one of your contacts. A contact still used by an expense
        (as payer, sharer or "paid to") or a settlement is refused: the
        database's foreign keys block the delete, and that becomes a 409.
        Deleting it would otherwise silently change history and balances.

    Parameters:
        counterparty_id: The contact to delete.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        Nothing (204), 404, or 409 if the contact is still used.
    """
    counterparty = get_owned_counterparty(db, current_user, counterparty_id)
    name = counterparty.name

    db.delete(counterparty)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{name} is used in expenses or settlements. Edit or "
                "delete those first, or rename the contact instead."
            ),
        )