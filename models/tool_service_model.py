from database import BaseModel
from sqlalchemy import CHAR, Column, ForeignKey, TEXT
from sqlalchemy.orm import relationship
import uuid


class ToolServiceModel(BaseModel):
    __tablename__ = "tool_service"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    product_delivery = Column(TEXT)
    product_marketer = Column(CHAR(36), ForeignKey("owners.id", name="fk_tool_service_marketer"))
    product_category = Column(TEXT)
    name = Column(TEXT)

    tool_status = Column(TEXT)
    availability_loc = Column(TEXT)

    product_type = Column(TEXT)
    description = Column(TEXT)

    marketer = relationship("OwnerModel", foreign_keys=[product_marketer], back_populates="tool_services")
    program_solutions = relationship("ProgramSolModel", foreign_keys="ProgramSolModel.tool_service_id", back_populates="tool_service")
