import os
from datetime import datetime, timedelta
from typing import Optional, Generator

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, Session, SQLModel, create_engine, select


DATABASE_URL = os.getenv("USER_DB_URL", "sqlite:///./services/user_service/user.db")
JWT_SECRET = os.getenv("USER_JWT_SECRET", "super-secret-key")
JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.getenv("USER_TOKEN_TTL_HOURS", "8"))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

bearer_scheme = HTTPBearer(auto_error=False)
app = FastAPI(title="User Service", version="1.0.0")


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    email: str = Field(index=True)
    password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class UserCreate(BaseModel):
    username: str = PydanticField(min_length=3, max_length=50)
    email: str
    password: str

class UserRead(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead

# --- db helpers ---
def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

# --- token helpers ---
def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(credentials: HTTPAuthorizationCredentials | None) -> User:
    if credentials is None:
        raise HTTPException(401, "Authorization header missing")

    token = credentials.credentials

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(401, "Invalid token")

    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(401, "User not found")
        return user

# --- startup ---
@app.on_event("startup")
def on_startup():
    create_db_and_tables()

# --- routes ---
@app.get("/health")
def health():
    return {"status": "ok", "service": "user"}

@app.post("/users/", response_model=UserRead, status_code=201)
def register_user(payload: UserCreate, session: Session = Depends(get_session)):
    if session.exec(select(User).where(User.username == payload.username)).first():
        raise HTTPException(400, "Username already exists")
    if session.exec(select(User).where(User.email == payload.email)).first():
        raise HTTPException(400, "Email already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        password=payload.password,   # stored as plain text
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == payload.username)).first()
    if not user or user.password != payload.password:
        raise HTTPException(401, "Invalid credentials")

    token = create_token(user)
    return TokenResponse(access_token=token, user=user)

@app.get("/users/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(decode_token)):
    return current_user

@app.get("/users/{user_id}", response_model=UserRead)
def read_user(user_id: int, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user
