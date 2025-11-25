import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select


DATABASE_URL = os.getenv("CATALOG_DB_URL", "sqlite:///./services/catalog_service/catalog.db")
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
app = FastAPI(title="Catalog Service", version="1.0.0")


class Book(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: str
    isbn: str = Field(index=True)
    total_copies: int = 1
    available_copies: int = 1


class BookPayload(BaseModel):
    title: str
    author: str
    isbn: str
    total_copies: int = 1
    available_copies: Optional[int] = None


class InventoryRequest(BaseModel):
    count: int = 1


def create_db():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


@app.on_event("startup")
def startup_event():
    create_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "catalog"}


@app.get("/books/")
def list_books(
    search: str | None = Query(default=None, description="Filter by title, author or ISBN"),
    session: Session = Depends(get_session),
):
    query = select(Book)
    if search:
        like = f"%{search.lower()}%"
        query = query.where(
            (Book.title.ilike(like)) | (Book.author.ilike(like)) | (Book.isbn.ilike(like))
        )
    books = session.exec(query).all()
    return books


@app.post("/books/", status_code=status.HTTP_201_CREATED)
def create_book(payload: BookPayload, session: Session = Depends(get_session)):
    if session.exec(select(Book).where(Book.isbn == payload.isbn)).first():
        raise HTTPException(status_code=400, detail="Book with this ISBN already exists")
    available = payload.available_copies if payload.available_copies is not None else payload.total_copies
    if available > payload.total_copies:
        raise HTTPException(status_code=400, detail="Available copies cannot exceed total copies")
    book = Book(
        title=payload.title,
        author=payload.author,
        isbn=payload.isbn,
        total_copies=payload.total_copies,
        available_copies=available,
    )
    session.add(book)
    session.commit()
    session.refresh(book)
    return book


@app.get("/books/{book_id}")
def read_book(book_id: int, session: Session = Depends(get_session)):
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.put("/books/{book_id}")
def update_book(book_id: int, payload: BookPayload, session: Session = Depends(get_session)):
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    available = payload.available_copies if payload.available_copies is not None else payload.total_copies
    if available > payload.total_copies:
        raise HTTPException(status_code=400, detail="Available copies cannot exceed total copies")

    book.title = payload.title
    book.author = payload.author
    book.isbn = payload.isbn
    book.total_copies = payload.total_copies
    book.available_copies = available

    session.add(book)
    session.commit()
    session.refresh(book)
    return book


@app.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, session: Session = Depends(get_session)):
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    session.delete(book)
    session.commit()
    return {"status": "deleted"}


@app.post("/books/{book_id}/reserve")
def reserve_book(book_id: int, payload: InventoryRequest, session: Session = Depends(get_session)):
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.available_copies < payload.count:
        raise HTTPException(status_code=400, detail="Not enough copies available")
    book.available_copies -= payload.count
    session.add(book)
    session.commit()
    session.refresh(book)
    return {"status": "reserved", "book": book}


@app.post("/books/{book_id}/release")
def release_book(book_id: int, payload: InventoryRequest, session: Session = Depends(get_session)):
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.available_copies + payload.count > book.total_copies:
        raise HTTPException(status_code=400, detail="Cannot exceed total copies")
    book.available_copies += payload.count
    session.add(book)
    session.commit()
    session.refresh(book)
    return {"status": "released", "book": book}


