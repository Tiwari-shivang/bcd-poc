from database import BaseModel
from sqlalchemy import Column, String, TEXT, TIMESTAMP, text as sa_text
from pgvector.sqlalchemy import Vector
import uuid
class EmbeddingModel(BaseModel):
    __tablename__="embeddings"
    id=Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    data=Column(Vector(1536), nullable=False)
    description=Column(TEXT, nullable=False)
    key=Column(TEXT, nullable=False)
    created_at=Column(TIMESTAMP(timezone=True), server_default=sa_text('now()'), nullable=False)
    updated_at=Column(TIMESTAMP(timezone=True), server_default=sa_text('now()'), nullable=False)