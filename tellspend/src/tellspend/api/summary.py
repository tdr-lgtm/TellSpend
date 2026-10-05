"""Route for the monthly summary shown on the Expenses page."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from tellspend.api.auth import get_current_user
from tellspend.api.schemas import MonthSummary
from tellspend.database.connection import get_db
from tellspend.database.models import User
from tellspend.services.summary import month_summary


router = APIRouter(
    tags=["summary"],
)


@router.get("/summary", response_model=MonthSummary)
def get_summary(
    month: str | None = Query(default=None, description="YYYY-MM; defaults to this month"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explanation:
        Totals for one month, per currency.

    Parameters:
        month: The month as YYYY-MM; defaults to this month.
        current_user: The signed-in user.
        db: The database session for this request.

    Returns:
        The month's summary, or 422 if the month is malformed.
    """
    month = month or dt.date.today().strftime("%Y-%m")

    try:
        return month_summary(db, current_user, month)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        )
