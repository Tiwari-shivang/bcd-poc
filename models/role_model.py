from database import BaseModel
from sqlalchemy import Column, String, TEXT
import uuid
class RoleModel(BaseModel):
    __tablename__="roles"
    id=Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name=Column(TEXT, nullable=False)