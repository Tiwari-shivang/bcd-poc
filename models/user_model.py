from database import BaseModel
from sqlalchemy import String, TEXT, Column, ForeignKey
from sqlalchemy.orm import relationship
import uuid

class UserModel(BaseModel):
    __tablename__="users"
    id=Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name=Column(String(50), nullable=False)
    last_name=Column(String(50), nullable=False)
    email=Column(TEXT, nullable=False)
    role_id=Column(String(36), ForeignKey("roles.id"))
    Role=relationship("RoleModel")