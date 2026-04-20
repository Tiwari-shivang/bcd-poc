from database import BaseModel
from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, TEXT, TIMESTAMP, VARCHAR, String, text as sa_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid


class AccountModel(BaseModel):
    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    name = Column(VARCHAR(100))
    is_deleted = Column(Boolean, nullable=False, server_default=sa_text("FALSE"))

    billing_address = Column(TEXT)
    shipping_address = Column(TEXT)

    phone = Column(VARCHAR(10))
    fax = Column(TEXT)

    owner_id = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_owner"))
    created_at = Column(TIMESTAMP)
    last_activity = Column(Date)

    national_svp = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_national_svp"))
    hotel_sol_business_owner = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_hotel_sol"))
    advito_business_owner = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_advito"))
    me_business_owner = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_me_owner"))
    bcd_business_owner = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_bcd_owner"))

    latam_ram = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_latam_ram"))
    emea_ram = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_emea_ram"))
    apac_ram = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_apac_ram"))
    na_ram = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_na_ram"))

    global_account_manager = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_gam"))
    global_executive_sponsor = Column(UUID(as_uuid=True), ForeignKey("owners.id", name="fk_accounts_ges"))

    advito_client_status = Column(TEXT)
    me_client_status = Column(TEXT)
    bcd_client_status = Column(TEXT)

    opportunity_count = Column(Integer)
    industry = Column(TEXT)

    owner = relationship("OwnerModel", foreign_keys=[owner_id], back_populates="owned_accounts")
    national_svp_owner = relationship("OwnerModel", foreign_keys=[national_svp], back_populates="national_svp_accounts")
    hotel_sol_owner = relationship("OwnerModel", foreign_keys=[hotel_sol_business_owner], back_populates="hotel_solution_accounts")
    advito_owner = relationship("OwnerModel", foreign_keys=[advito_business_owner], back_populates="advito_accounts")
    me_owner = relationship("OwnerModel", foreign_keys=[me_business_owner], back_populates="me_accounts")
    bcd_owner = relationship("OwnerModel", foreign_keys=[bcd_business_owner], back_populates="bcd_accounts")
    latam_ram_owner = relationship("OwnerModel", foreign_keys=[latam_ram], back_populates="latam_ram_accounts")
    emea_ram_owner = relationship("OwnerModel", foreign_keys=[emea_ram], back_populates="emea_ram_accounts")
    apac_ram_owner = relationship("OwnerModel", foreign_keys=[apac_ram], back_populates="apac_ram_accounts")
    na_ram_owner = relationship("OwnerModel", foreign_keys=[na_ram], back_populates="na_ram_accounts")
    global_account_manager_owner = relationship("OwnerModel", foreign_keys=[global_account_manager], back_populates="global_account_manager_accounts")
    global_executive_sponsor_owner = relationship("OwnerModel", foreign_keys=[global_executive_sponsor], back_populates="global_executive_sponsor_accounts")
    agreements = relationship("AgreementModel", foreign_keys="AgreementModel.account_id", back_populates="account")
    gcn_records = relationship("GCNModel", foreign_keys="GCNModel.account_id", back_populates="account")
