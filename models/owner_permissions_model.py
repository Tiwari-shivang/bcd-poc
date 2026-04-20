from database import BaseModel
from sqlalchemy import Column, ForeignKey, String


class OwnerPermissionsModel(BaseModel):
    __tablename__ = "owner_permissions"

    owner_id = Column(String(36), ForeignKey("owners.id", ondelete="CASCADE"), primary_key=True)
    permission_id = Column(String(36), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)
