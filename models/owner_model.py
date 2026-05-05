from database import BaseModel
from sqlalchemy import Boolean, Column, Enum, Numeric, TEXT, TIMESTAMP, String, VARCHAR, text as sa_text
from sqlalchemy.orm import relationship
import uuid

COMPANY_ENUM = ("BCD Travel", "Advito", "EMEA")


class OwnerModel(BaseModel):
    __tablename__ = "owners"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    name = Column(TEXT)
    role = Column(TEXT)
    alias = Column(TEXT)
    license = Column(TEXT)

    email = Column(TEXT)
    email_status = Column(Boolean)

    profile = Column(TEXT)
    username = Column(TEXT)

    company = Column(Enum(*COMPANY_ENUM, name="company_enum"))
    time_zone = Column(TIMESTAMP(timezone=True))

    division = Column(TEXT)
    locale = Column(TEXT)

    manager = Column(TEXT)
    mobile = Column(VARCHAR(15))

    last_login = Column(TIMESTAMP)
    created_by = Column(TEXT)

    cost_center = Column(Numeric)

    ownership_type = Column(TEXT)

    me_sales_goal_usd = Column(Numeric)

    is_frozen = Column(Boolean, server_default=sa_text("FALSE"))
    created_at = Column(TIMESTAMP, server_default=sa_text("CURRENT_TIMESTAMP"))

    owned_accounts = relationship("AccountModel", foreign_keys="AccountModel.owner_id", back_populates="owner")
    national_svp_accounts = relationship("AccountModel", foreign_keys="AccountModel.national_svp", back_populates="national_svp_owner")
    hotel_solution_accounts = relationship("AccountModel", foreign_keys="AccountModel.hotel_sol_business_owner", back_populates="hotel_sol_owner")
    advito_accounts = relationship("AccountModel", foreign_keys="AccountModel.advito_business_owner", back_populates="advito_owner")
    me_accounts = relationship("AccountModel", foreign_keys="AccountModel.me_business_owner", back_populates="me_owner")
    bcd_accounts = relationship("AccountModel", foreign_keys="AccountModel.bcd_business_owner", back_populates="bcd_owner")
    latam_ram_accounts = relationship("AccountModel", foreign_keys="AccountModel.latam_ram", back_populates="latam_ram_owner")
    emea_ram_accounts = relationship("AccountModel", foreign_keys="AccountModel.emea_ram", back_populates="emea_ram_owner")
    apac_ram_accounts = relationship("AccountModel", foreign_keys="AccountModel.apac_ram", back_populates="apac_ram_owner")
    na_ram_accounts = relationship("AccountModel", foreign_keys="AccountModel.na_ram", back_populates="na_ram_owner")
    global_account_manager_accounts = relationship("AccountModel", foreign_keys="AccountModel.global_account_manager", back_populates="global_account_manager_owner")
    global_executive_sponsor_accounts = relationship("AccountModel", foreign_keys="AccountModel.global_executive_sponsor", back_populates="global_executive_sponsor_owner")
    owned_agreements = relationship("AgreementModel", foreign_keys="AgreementModel.owner_id", back_populates="owner")
    vp_agreements = relationship("AgreementModel", foreign_keys="AgreementModel.agreement_vp", back_populates="agreement_vp_owner")
    tool_services = relationship("ToolServiceModel", foreign_keys="ToolServiceModel.product_marketer", back_populates="marketer")
