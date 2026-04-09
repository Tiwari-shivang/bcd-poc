from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os
load_dotenv()

DB_URL=os.getenv("DB_URL")

engine = create_engine(DB_URL)

session = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

BaseModel = declarative_base()

def get_db():
    db=session()
    try:
        yield db
    finally:
        db.close()