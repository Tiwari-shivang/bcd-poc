from database import BaseModel
from sqlalchemy import Column, String, TIMESTAMP, TEXT, ForeignKey
from sqlalchemy.orm import relationship
import uuid
class LeaveModel(BaseModel):
    __tablename__="leaves"
    id=Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    from_date=Column(TIMESTAMP, nullable=False)
    to_date=Column(TIMESTAMP, nullable=False)
    status=Column(String(30), nullable=False)
    reason=Column(TEXT, nullable=False)
    user_id=Column(String(36), ForeignKey("users.id"))
    User=relationship("UserModel")