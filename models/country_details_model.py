from database import BaseModel
from sqlalchemy import Column, ForeignKey, String, TEXT
from sqlalchemy.orm import relationship
import uuid


class CountryDetailsModel(BaseModel):
    __tablename__ = "countries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"))

    name = Column(TEXT)
    region = Column(TEXT)

    agreement_status = Column(TEXT)
    country_status = Column(TEXT)

    booking_country = Column(TEXT)
    ticket_country = Column(TEXT)

    agreement = relationship("AgreementModel", foreign_keys=[agreement_id], back_populates="country_details")
