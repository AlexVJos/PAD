import asyncio
import os
from typing import Optional

from fastapi import Depends, FastAPI
from sqlmodel import Field, Session, SQLModel, create_engine, select

from services.shared.messaging import consume_events


DATABASE_URL = os.getenv("ANALYTICS_DB_URL", "sqlite:///./services/analytics_service/analytics.db")
AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@rabbitmq:5672/")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
app = FastAPI(title="Analytics Service", version="1.0.0")


class AggregateMetric(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    total_loans: int = Field(default=0)
    active_loans: int = Field(default=0)
    total_returns: int = Field(default=0)


class UserMetric(SQLModel, table=True):
    user_id: int = Field(primary_key=True)
    loans_taken: int = Field(default=0)
    loans_returned: int = Field(default=0)


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def get_or_create_aggregate(session: Session) -> AggregateMetric:
    metric = session.get(AggregateMetric, 1)
    if not metric:
        metric = AggregateMetric()
        session.add(metric)
        session.commit()
        session.refresh(metric)
    return metric


def get_or_create_user_metric(session: Session, user_id: int) -> UserMetric:
    metric = session.get(UserMetric, user_id)
    if not metric:
        metric = UserMetric(user_id=user_id)
        session.add(metric)
        session.commit()
        session.refresh(metric)
    return metric


async def event_handler(event: dict) -> None:
    event_type = event.get("type")
    payload = event.get("payload", {})
    user_id = payload.get("user_id")

    with Session(engine) as session:
        aggregate = get_or_create_aggregate(session)
        if user_id is not None:
            user_metric = get_or_create_user_metric(session, int(user_id))
        else:
            user_metric = None

        if event_type == "loan.created":
            aggregate.total_loans += 1
            aggregate.active_loans += 1
            if user_metric:
                user_metric.loans_taken += 1
        elif event_type == "loan.returned":
            aggregate.total_returns += 1
            aggregate.active_loans = max(0, aggregate.active_loans - 1)
            if user_metric:
                user_metric.loans_returned += 1

        session.add(aggregate)
        if user_metric:
            session.add(user_metric)
        session.commit()


async def start_consumer():
    while True:
        try:
            await consume_events(
                AMQP_URL,
                queue_name="analytics-queue",
                binding_keys=["loan.*"],
                handler=event_handler,
            )
        except Exception:  # pragma: no cover - resilience path
            await asyncio.sleep(5)


@app.on_event("startup")
async def startup_event():
    create_db()
    asyncio.create_task(start_consumer())


@app.get("/health")
def health():
    return {"status": "ok", "service": "analytics"}


@app.get("/metrics/summary")
def summary(session: Session = Depends(get_session)):
    metrics = get_or_create_aggregate(session)
    return metrics


@app.get("/metrics/users/{user_id}")
def user_metrics(user_id: int, session: Session = Depends(get_session)):
    metric = session.get(UserMetric, user_id)
    if not metric:
        metric = UserMetric(user_id=user_id)
    return metric


