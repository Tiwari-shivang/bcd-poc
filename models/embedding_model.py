from database import BaseModel
from sqlalchemy import Column, String, TEXT, TIMESTAMP
import uuid
class EmbeddingModel(BaseModel):
    __tablename__="embeddings"
    id=Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    data=Column(TEXT, nullable=False)
    description=Column(TEXT, nullable=False)
    key=Column(TEXT, nullable=False)
    created_at=Column(TIMESTAMP, nullable=False)
    updated_at=Column(TIMESTAMP, nullable=False)