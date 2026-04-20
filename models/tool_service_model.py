from database import BaseModel
from sqlalchemy import Column, TEXT, String
import uuid

class ToolServiceModel(BaseModel):
    __tablename__="tool_services"
    id=Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    