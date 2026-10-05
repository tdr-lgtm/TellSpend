from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from tellspend.database.connection import get_db
from tellspend.api.auth_routes import router as auth_router
from tellspend.api.users import router as users_router
from tellspend.api.expenses import router as expenses_router
from tellspend.api.categories import router as categories_router
from tellspend.api.counterparties import router as counterparties_router
from tellspend.api.settlements import router as settlements_router
from tellspend.api.summary import router as summary_router
from tellspend.api.assistant import router as assistant_router
from tellspend.api.expected import router as expected_router

app = FastAPI(
    title="TellSpend API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"^http://"
        r"(localhost|127\.0\.0\.1|"
        r"192\.168\.\d+\.\d+|"
        r"10\.\d+\.\d+\.\d+):5173$"
    ),
    allow_origins=["https://tell-spend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable.",
        )

    return {"status": "ok", "database": "ok"}

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(expenses_router)
app.include_router(categories_router)
app.include_router(counterparties_router)
app.include_router(settlements_router)
app.include_router(summary_router)
app.include_router(assistant_router)
app.include_router(expected_router)
