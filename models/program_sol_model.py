from database import BaseModel
from sqlalchemy import CHAR, Column, Date, Enum, ForeignKey, TEXT
from sqlalchemy.orm import relationship
import uuid

PROGRAM_SOL_STATUS_ENUM = (
    "Implemented",
    "De-Implemented",
    "In Scope",
    "In Vetting",
    "Never Implemented",
)


class ProgramSolModel(BaseModel):
    __tablename__ = "program_sol"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    name = Column(TEXT)

    country_id = Column(CHAR(36), ForeignKey("countries.id", name="fk_program_sol_country"))
    product_type = Column(TEXT)

    status = Column(Enum(*PROGRAM_SOL_STATUS_ENUM, name="program_sol_status_enum"))
    trial_exp_date = Column(Date)

    tool_service_id = Column(CHAR(36), ForeignKey("tool_service.id", name="fk_program_sol_tool_service"))
    agreement_id = Column(CHAR(36), ForeignKey("agreements.id", name="fk_program_sol_agreement"))

    country = relationship("CountryDetailsModel", foreign_keys=[country_id], back_populates="program_solutions")
    tool_service = relationship("ToolServiceModel", foreign_keys=[tool_service_id], back_populates="program_solutions")
    agreement = relationship("AgreementModel", foreign_keys=[agreement_id], back_populates="program_solutions")
