from database import BaseModel
from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String, TEXT
from sqlalchemy.orm import relationship
import uuid

GCN_STATUS_ENUM = ("ZZ Archived", "Active")


class GCNModel(BaseModel):
    __tablename__ = "gcn"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"))

    status = Column(Enum(*GCN_STATUS_ENUM, name="gcn_status_enum"))
    client_name = Column(TEXT)
    case_number = Column(TEXT)

    is_me_gcn = Column(Boolean)
    client_exp_years = Column(Integer)

    account = relationship("AccountModel", foreign_keys=[account_id], back_populates="gcn_records")
