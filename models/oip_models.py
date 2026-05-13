from database import OIPBase
from sqlalchemy import CHAR, Column, ForeignKey, INTEGER, TEXT, TIMESTAMP, VARCHAR


class OIPAccountModel(OIPBase):
    __tablename__ = "accounts"
    id = Column(INTEGER, primary_key=True)
    sf_id = Column(VARCHAR(18))
    name = Column(VARCHAR(255))
    address = Column(TEXT)
    created_at = Column(VARCHAR(20))
    updated_at = Column(VARCHAR(20))


class OIPCustomerModel(OIPBase):
    __tablename__ = "customers"
    id = Column(CHAR(36), primary_key=True)
    sf_id = Column(VARCHAR(255))
    global_customer_name = Column(VARCHAR(255))
    global_customer_number = Column(VARCHAR(255))
    gcn_type = Column(VARCHAR(100))
    status = Column(VARCHAR(100))
    cbc_case_safe_id = Column(VARCHAR(255))
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)


class OIPOpportunityModel(OIPBase):
    __tablename__ = "opportunities"
    id = Column(CHAR(36), primary_key=True)
    name = Column(VARCHAR(255))
    sf_case_safe_id = Column(VARCHAR(255))
    sales_category = Column(VARCHAR(100))
    record_type = Column(VARCHAR(100))
    isd_status = Column(VARCHAR(100))
    created_at = Column(TIMESTAMP)
    account_id = Column(INTEGER, ForeignKey("accounts.id"))
    customer_id = Column(CHAR(36), ForeignKey("customers.id"))


class OIPCountryModel(OIPBase):
    __tablename__ = "countries"
    id = Column(CHAR(36), primary_key=True)
    name = Column(VARCHAR(100))
    iso_code = Column(VARCHAR(10))
    created_at = Column(TIMESTAMP)


class OIPCountryDetailsModel(OIPBase):
    __tablename__ = "country_details"
    id = Column(CHAR(36), primary_key=True)
    case_safe_id = Column(VARCHAR(255))
    ticketing_country_id = Column(CHAR(36), ForeignKey("countries.id"))
    servicing_country_id = Column(CHAR(36), ForeignKey("countries.id"))
    invoicing_agency = Column(VARCHAR(255))
    servicing_agency = Column(VARCHAR(255))
    created_at = Column(TIMESTAMP)


class OIPProjectModel(OIPBase):
    __tablename__ = "projects"
    id = Column(CHAR(36), primary_key=True)
    name = Column(VARCHAR(255))
    project_configuration_id = Column(VARCHAR(255))
    opportunity_id = Column(CHAR(36), ForeignKey("opportunities.id"))
    project_country_id = Column(CHAR(36), ForeignKey("countries.id"))
    traveller_country_id = Column(CHAR(36), ForeignKey("countries.id"))
    country_details_id = Column(CHAR(36), ForeignKey("country_details.id"))
    created_at = Column(TIMESTAMP)


class OIPDecisionSourceModel(OIPBase):
    __tablename__ = "decision_sources"
    id = Column(CHAR(36), primary_key=True)
    case_safe_id = Column(VARCHAR(255))
    created_at = Column(TIMESTAMP)


class OIPServiceConfigModel(OIPBase):
    __tablename__ = "service_config"
    id = Column(CHAR(36), primary_key=True)
    service_configuration = Column(VARCHAR(255))
    service_segmentation = Column(VARCHAR(255))
    created_at = Column(TIMESTAMP)


class OIPSolutionModel(OIPBase):
    __tablename__ = "solutions"
    id = Column(CHAR(36), primary_key=True)
    tool_service_sf_id = Column(VARCHAR(255))
    program_solution_case_safe_id = Column(VARCHAR(255))
    tool_or_service = Column(VARCHAR(255))
    product_type_id = Column(VARCHAR(255))
    product_type = Column(VARCHAR(255))
    solution_status_id = Column(VARCHAR(255))
    solution_status = Column(VARCHAR(100))
    record_type = Column(VARCHAR(100))
    status_id = Column(VARCHAR(255))
    final_status = Column(VARCHAR(100))
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
    account_id = Column(INTEGER, ForeignKey("accounts.id"))
    opportunity_id = Column(CHAR(36), ForeignKey("opportunities.id"))
    project_id = Column(CHAR(36), ForeignKey("projects.id"))
    decision_source_id = Column(CHAR(36), ForeignKey("decision_sources.id"))
    service_config_id = Column(CHAR(36), ForeignKey("service_config.id"))
    country_details_id = Column(CHAR(36), ForeignKey("country_details.id"))


class OIPSRQRequestModel(OIPBase):
    __tablename__ = "srq_requests"
    id = Column(CHAR(36), primary_key=True)
    srq_number = Column(VARCHAR(255))
    srq_name = Column(VARCHAR(255))
    service_config_id = Column(CHAR(36), ForeignKey("service_config.id"))
