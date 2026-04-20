from database import BaseModel
from sqlalchemy import TEXT, Column, String
import uuid

class PermissionModel(BaseModel):
    __tablename__="permissions"
    id=Column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    name=Column(TEXT, nullable=False)