## Table: accounts

### Columns

* id (varchar(36), Primary Key, Default: uuid.uuid4())
* name (varchar(100))
* is_deleted (boolean, Not Null, Default: FALSE)
* billing_address (text)
* shipping_address (text)
* phone (varchar(15))
* fax (text)
* owner_id (varchar(36), Foreign Key -> owners.id)
* created_at (timestamp)
* last_activity (date)
* national_svp (char(36), Foreign Key -> owners.id)
* hotel_sol_business_owner (char(36), Foreign Key -> owners.id)
* advito_business_owner (char(36), Foreign Key -> owners.id)
* me_business_owner (char(36), Foreign Key -> owners.id)
* bcd_business_owner (char(36), Foreign Key -> owners.id)
* latam_ram (char(36), Foreign Key -> owners.id)
* emea_ram (char(36), Foreign Key -> owners.id)
* apac_ram (char(36), Foreign Key -> owners.id)
* na_ram (char(36), Foreign Key -> owners.id)
* global_account_manager (char(36), Foreign Key -> owners.id)
* global_executive_sponsor (char(36), Foreign Key -> owners.id)
* advito_client_status (enum: Client, Prospect, N/A)
* me_client_status (enum: Client, Prospect, N/A)
* bcd_client_status (enum: Client, Prospect, N/A)
* opportunity_count (integer)
* industry (text)

---

## Table: agreements

### Columns

* id (varchar(36), Primary Key, Default: uuid.uuid4())
* name (varchar(100))
* account_id (varchar(36), Foreign Key -> accounts.id)
* gcn_id (varchar(36), Foreign Key -> gcn.id)
* contract_type (enum: Single Country, Global, National Agreement, Multinational, Regional, Regional Agreement, Local Agreement)
* region (text)
* status (enum: Closed Consolidated, Lost, Pending Contract, Signed and Finalized, Servicing Without a Contract)
* effective_date (date)
* agreement_end_date (date)
* agreement_vp (varchar(36), Foreign Key -> owners.id)
* owner_id (varchar(36), Foreign Key -> owners.id)
* renewal_terms (enum: N/A, By Agreement Only, Automatic Renewal, Evergreen)

---

## Table: annual_vol

### Columns

* id (char(36), Primary Key, Default: uuid.uuid4())
* name (text)
* country_id (char(36), Foreign Key -> countries.id)
* agreement_id (char(36), Foreign Key -> agreements.id)
* air_transaction (integer)
* air_vol (numeric)
* train_transaction (integer)
* train_vol (numeric)
* car_transaction (integer)
* car_vol (numeric)
* hotel_transaction (integer)
* hotel_vol (numeric)
* currency_iso_code (char(5))

---

## Table: countries

### Columns

* id (varchar(36), Primary Key, Default: uuid.uuid4())
* agreement_id (varchar(36), Foreign Key -> agreements.id, On Delete: CASCADE)
* name (text)
* region (text)
* country_status (enum: Implemented, In Scope, De-Implemented, Pending De-implementation, In Vetting)
* booking_country (text)
* ticket_country (text)

---

## Table: gcn

### Columns

* id (varchar(36), Primary Key, Default: uuid.uuid4())
* account_id (varchar(36), Foreign Key -> accounts.id, On Delete: CASCADE)
* status (enum: ZZ Archived, Active)
* client_name (text)
* case_number (text)
* is_me_gcn (boolean)
* client_exp_years (integer)

---

## Table: owner_permissions

### Columns

* owner_id (varchar(36), Primary Key, Foreign Key -> owners.id, On Delete: CASCADE)
* permission_id (varchar(36), Primary Key, Foreign Key -> permissions.id, On Delete: CASCADE)

---

## Table: owners

### Columns

* id (varchar(36), Primary Key, Default: uuid.uuid4())
* name (text, Not Null)
* role (text, Not Null)
* alias (text, Not Null)
* license (text, Not Null)
* email (text, Unique, Not Null)
* email_status (boolean, Not Null)
* profile (text)
* username (text, Unique)
* company (enum: BCD Travel, Advito, EMEA, Not Null)
* time_zone (timestamp with time zone)
* division (text)
* locale (text)
* manager (text)
* mobile (varchar(15))
* last_login (timestamp)
* created_by (text)
* cost_center (numeric)
* ownership_type (text)
* me_sales_goal_usd (numeric)
* is_frozen (boolean, Not Null, Default: FALSE)
* created_at (timestamp, Not Null, Default: CURRENT_TIMESTAMP)

---

## Table: permissions

### Columns

* id (varchar(36), Primary Key, Default: uuid.uuid4())
* name (text, Not Null)

---

## Table: program_sol

### Columns

* id (char(36), Primary Key, Default: uuid.uuid4())
* name (text)
* country_id (char(36), Foreign Key -> countries.id)
* product_type (text)
* status (enum: Implemented, De-Implemented, In Scope, In Vetting, Never Implemented)
* trial_exp_date (date)
* tool_service_id (char(36), Foreign Key -> tool_service.id)
* agreement_id (char(36), Foreign Key -> agreements.id)

---

## Table: tool_service

### Columns

* id (char(36), Primary Key, Default: uuid.uuid4())
* product_delivery (text)
* product_marketer (char(36), Foreign Key -> owners.id)
* product_category (text)
* name (text)
* tool_status (enum: Active, Inactive, In Development)
* availability_loc (enum: Ticketing, Booking, Customer)
* product_type (text)
* description (text)
