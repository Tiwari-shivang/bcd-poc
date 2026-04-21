from database import BaseModel
from sqlalchemy import Column, Enum, ForeignKey, String, TEXT
from sqlalchemy.orm import relationship
import uuid

COUNTRY_STATUS_ENUM = (
    "Implemented",
    "In Scope",
    "De-Implemented",
    "Pending De-implementation",
    "In Vetting",
)


class CountryDetailsModel(BaseModel):
    __tablename__ = "countries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"))

    name = Column(TEXT)
    region = Column(TEXT)

    country_status = Column(Enum(*COUNTRY_STATUS_ENUM, name="country_status_enum"))

    booking_country = Column(TEXT)
    ticket_country = Column(TEXT)

    agreement = relationship("AgreementModel", foreign_keys=[agreement_id], back_populates="country_details")
    annual_volumes = relationship("AnnualVolModel", foreign_keys="AnnualVolModel.country_id", back_populates="country")
    program_solutions = relationship("ProgramSolModel", foreign_keys="ProgramSolModel.country_id", back_populates="country")
