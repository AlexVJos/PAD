import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select

from services.shared.messaging import publish_event


DATABASE_URL = os.getenv("LOAN_DB_URL", "sqlite:///./services/loan_service/loan.db")
CATALOG_URL = os.getenv("CATALOG_SERVICE_URL", "http://catalog-service:8002")
AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@rabbitmq:5672/")
LOAN_PERIOD_DAYS = int(os.getenv("LOAN_PERIOD_DAYS", "14"))

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
app = FastAPI(title="Loan Service", version="1.0.0")


class Loan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    user_name: str
    book_id: int
    book_title: str
    loan_date: datetime = Field(default_factory=datetime.utcnow)
    due_date: datetime
    returned_date: datetime | None = None
    status: str = Field(default="active")


class LoanCreate(BaseModel):
    user_id: int
    user_name: str
    book_id: int


class LoanRead(BaseModel):
    id: int
    user_id: int
    user_name: str
    book_id: int
    book_title: str
    loan_date: datetime
    due_date: datetime
    returned_date: datetime | None
    status: str

    class Config:
        orm_mode = True


class LoanReturnRequest(BaseModel):
    user_id: int


class LoanReturnResponse(BaseModel):
    status: str
    loan: LoanRead


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


async def get_http_client() -> httpx.AsyncClient:
    if not hasattr(app.state, "http_client"):
        app.state.http_client = httpx.AsyncClient(timeout=10.0)
    return app.state.http_client


@app.on_event("startup")
async def startup_event():
    create_db()
    await get_http_client()


@app.on_event("shutdown")
async def shutdown_event():
    client = getattr(app.state, "http_client", None)
    if client:
        await client.aclose()


@app.get("/health")
def health():
    return {"status": "ok", "service": "loan"}


async def fetch_book(book_id: int) -> dict:
    client = await get_http_client()
    try:
        response = await client.get(f"{CATALOG_URL}/books/{book_id}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Catalog service unavailable") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Book not found")
    response.raise_for_status()
    return response.json()


async def adjust_inventory(book_id: int, action: str, count: int = 1) -> None:
    endpoint = f"{CATALOG_URL}/books/{book_id}/{action}"
    client = await get_http_client()
    try:
        response = await client.post(endpoint, json={"count": count})
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Catalog service unavailable") from exc
    if response.status_code >= 400:
        detail = response.json().get("detail") if response.headers.get("content-type") == "application/json" else response.text
        raise HTTPException(status_code=response.status_code, detail=detail or "Inventory update failed")


@app.get("/loans/", response_model=list[LoanRead])
def list_loans(
    user_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, description="Filter by status"),
    session: Session = Depends(get_session),
):
    query = select(Loan)
    if user_id:
        query = query.where(Loan.user_id == user_id)
    if status_filter:
        query = query.where(Loan.status == status_filter)
    loans = session.exec(query.order_by(Loan.loan_date.desc())).all()
    return loans


@app.post("/loans/", response_model=LoanRead, status_code=status.HTTP_201_CREATED)
async def create_loan(payload: LoanCreate, session: Session = Depends(get_session)):
    book = await fetch_book(payload.book_id)
    if book["available_copies"] <= 0:
        raise HTTPException(status_code=400, detail="No available copies")

    existing = session.exec(
        select(Loan).where(
            (Loan.user_id == payload.user_id) & (Loan.book_id == payload.book_id) & (Loan.status == "active")
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Active loan already exists for this user and book")

    await adjust_inventory(payload.book_id, "reserve", 1)

    loan = Loan(
        user_id=payload.user_id,
        user_name=payload.user_name,
        book_id=payload.book_id,
        book_title=book["title"],
        due_date=datetime.utcnow() + timedelta(days=LOAN_PERIOD_DAYS),
    )
    session.add(loan)
    session.commit()
    session.refresh(loan)

    await publish_event(
        AMQP_URL,
        "loan.created",
        {
            "loan_id": loan.id,
            "user_id": loan.user_id,
            "user_name": loan.user_name,
            "book_id": loan.book_id,
            "book_title": loan.book_title,
            "due_date": loan.due_date.isoformat(),
        },
    )
    return loan


@app.post("/loans/{loan_id}/return", response_model=LoanReturnResponse)
async def return_loan(loan_id: int, payload: LoanReturnRequest, session: Session = Depends(get_session)):
    loan = session.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.user_id != payload.user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if loan.status == "returned":
        raise HTTPException(status_code=400, detail="Loan already returned")

    loan.status = "returned"
    loan.returned_date = datetime.utcnow()
    session.add(loan)
    session.commit()
    session.refresh(loan)

    await adjust_inventory(loan.book_id, "release", 1)
    await publish_event(
        AMQP_URL,
        "loan.returned",
        {
            "loan_id": loan.id,
            "user_id": loan.user_id,
            "user_name": loan.user_name,
            "book_id": loan.book_id,
            "book_title": loan.book_title,
            "returned_date": loan.returned_date.isoformat(),
        },
    )
    return LoanReturnResponse(status="returned", loan=loan)


@app.get("/loans/{loan_id}", response_model=LoanRead)
def read_loan(loan_id: int, session: Session = Depends(get_session)):
    loan = session.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


