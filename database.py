from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

# Salesforce / BCD execution database (domain schema only — no embeddings)
DB_URL = os.getenv("DB_URL")
# OIP warehouse execution (optional)
DB_URL_OIP = os.getenv("DB_URL_OIP")
# Isolated PostgreSQL holding only the `embeddings` table (+ pgvector)
DB_URL_VECTOR = os.getenv("DB_URL_VECTOR") or os.getenv("DB_VECTOR")

if not DB_URL:
    raise RuntimeError("DB_URL must be set (Salesforce/BCD execution database).")
if not DB_URL_VECTOR:
    raise RuntimeError(
        "Set DB_URL_VECTOR or DB_VECTOR to a PostgreSQL URL for the catalogue "
        "database (`embeddings` table, pgvector). Execution databases "
        "(DB_URL / DB_URL_OIP) do not store vectors."
    )

engine = create_engine(DB_URL)
session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
BaseModel = declarative_base()
OIPBase = declarative_base()

vector_engine = create_engine(DB_URL_VECTOR)
session_vector = sessionmaker(
    bind=vector_engine,
    autocommit=False,
    autoflush=False,
)
VectorBase = declarative_base()

engine_oip = create_engine(DB_URL_OIP) if DB_URL_OIP else None
session_oip = (
    sessionmaker(bind=engine_oip, autocommit=False, autoflush=False)
    if engine_oip
    else None
)


def get_db():
    """Salesforce / BCD execution session."""
    db = session()
    try:
        yield db
    finally:
        db.close()


def get_db_vector():
    """Embedding catalogue session (single `embeddings` table)."""
    db = session_vector()
    try:
        yield db
    finally:
        db.close()


def get_optional_db_oip():
    if session_oip is None:
        yield None
        return
    db = session_oip()
    try:
        yield db
    finally:
        db.close()


def oip_query_engine_configured() -> bool:
    return session_oip is not None
