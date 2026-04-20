from database import BaseModel
from sqlalchemy import Column, Date, ForeignKey, String, TEXT, VARCHAR
from sqlalchemy.orm import relationship
import uuid


class AgreementModel(BaseModel):
    __tablename__ = "agreements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    name = Column(VARCHAR(100))

    account_id = Column(String(36), ForeignKey("accounts.id", name="fk_agreement_account"))
    contact_type = Column(TEXT)
    region = Column(TEXT)
    status = Column(TEXT)

    effective_date = Column(Date)
    agreement_end_date = Column(Date)

    agreement_vp = Column(String(36), ForeignKey("owners.id", name="fk_agreement_vp"))
    owner_id = Column(String(36), ForeignKey("owners.id", name="fk_agreement_owner"))

    renewal_terms = Column(TEXT)

    account = relationship("AccountModel", foreign_keys=[account_id], back_populates="agreements")
    owner = relationship("OwnerModel", foreign_keys=[owner_id], back_populates="owned_agreements")
    agreement_vp_owner = relationship("OwnerModel", foreign_keys=[agreement_vp], back_populates="vp_agreements")
    country_details = relationship("CountryDetailsModel", foreign_keys="CountryDetailsModel.agreement_id", back_populates="agreement")
