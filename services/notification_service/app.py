import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Query
from sqlmodel import Field, Session, SQLModel, create_engine, select

from services.shared.messaging import consume_events


DATABASE_URL = os.getenv("NOTIFICATION_DB_URL", "sqlite:///./services/notification_service/notifications.db")
AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@rabbitmq:5672/")
RUN_EVENT_CONSUMER = os.getenv("RUN_EVENT_CONSUMER", "true").lower() == "true"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
app = FastAPI(title="Notification Service", version="1.0.0")
logger = logging.getLogger("notification-service")


class Notification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    user_name: str
    book_title: str
    event_type: str
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    delivered: bool = Field(default=False)


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


async def event_handler(event: dict) -> None:
    event_type = event.get("type", "unknown")
    payload = event.get("payload", {})
    message = ""

    if event_type == "loan.created":
        message = f"{payload.get('user_name')} взял книгу \"{payload.get('book_title')}\"."
    elif event_type == "loan.returned":
        message = f"{payload.get('user_name')} вернул книгу \"{payload.get('book_title')}\"."
    else:
        message = f"Получено событие {event_type}"

    notification = Notification(
        user_id=payload.get("user_id", 0),
        user_name=payload.get("user_name", "unknown"),
        book_title=payload.get("book_title", "unknown"),
        event_type=event_type,
        message=message,
    )

    with Session(engine) as session:
        session.add(notification)
        session.commit()


async def start_consumer():
    while True:
        try:
            await consume_events(
                AMQP_URL,
                queue_name="notification-queue",
                binding_keys=["loan.*"],
                handler=event_handler,
            )
        except Exception as exc:  # pragma: no cover - resilience path
            logger.exception("Notification consumer crashed: %s", exc)
            await asyncio.sleep(5)


@app.on_event("startup")
async def startup_event():
    create_db()
    if RUN_EVENT_CONSUMER:
        asyncio.create_task(start_consumer())


@app.get("/health")
def health():
    return {"status": "ok", "service": "notification"}


@app.get("/notifications/")
def list_notifications(
    user_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
):
    query = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    if user_id is not None:
        query = query.where(Notification.user_id == user_id)
    notifications = session.exec(query).all()
    return notifications


