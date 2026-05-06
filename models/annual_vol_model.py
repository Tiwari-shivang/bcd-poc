from database import BaseModel
from sqlalchemy import CHAR, Column, ForeignKey, Integer, Numeric, TEXT
from sqlalchemy.orm import relationship
import uuid


class AnnualVolModel(BaseModel):
    __tablename__ = "annual_vol"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    name = Column(TEXT)

    country_id = Column(CHAR(36), ForeignKey("countries.id", name="fk_annual_vol_country"))
    agreement_id = Column(CHAR(36), ForeignKey("agreements.id", name="fk_annual_vol_agreement"))

    air_transaction = Column(Integer)
    air_vol = Column(Numeric)

    train_transaction = Column(Integer)
    train_vol = Column(Numeric)

    car_transaction = Column(Integer)
    car_vol = Column(Numeric)

    hotel_transaction = Column(Integer)
    hotel_vol = Column(Numeric)

    currency_iso_code = Column(CHAR(5))

    country = relationship("CountryDetailsModel", foreign_keys=[country_id], back_populates="annual_volumes")
    agreement = relationship("AgreementModel", foreign_keys=[agreement_id], back_populates="annual_volumes")
