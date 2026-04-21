## Table: accounts

### Columns

- id (varchar(36), Primary Key, Default: uuid.uuid4())
- name (varchar(100))
- is_deleted (boolean, Not Null, Default: FALSE)
- billing_address (text)
- shipping_address (text)
- phone (varchar(10))
- fax (text)
- owner_id (varchar(36), Foreign Key -> owners.id)
- created_at (timestamp)
- last_activity (date)
- national_svp (char(36), Foreign Key -> owners.id)
- hotel_sol_business_owner (char(36), Foreign Key -> owners.id)
- advito_business_owner (char(36), Foreign Key -> owners.id)
- me_business_owner (char(36), Foreign Key -> owners.id)
- bcd_business_owner (char(36), Foreign Key -> owners.id)
- latam_ram (char(36), Foreign Key -> owners.id)
- emea_ram (char(36), Foreign Key -> owners.id)
- apac_ram (char(36), Foreign Key -> owners.id)
- na_ram (char(36), Foreign Key -> owners.id)
- global_account_manager (char(36), Foreign Key -> owners.id)
- global_executive_sponsor (char(36), Foreign Key -> owners.id)
- advito_client_status (enum: Client, Prospect, N/A)
- me_client_status (enum: Client, Prospect, N/A)
- bcd_client_status (enum: Client, Prospect, N/A)
- opportunity_count (integer)
- industry (text)

### Relationships

- accounts.owner_id -> owners.id (Many-to-One)
- accounts.national_svp -> owners.id (Many-to-One)
- accounts.hotel_sol_business_owner -> owners.id (Many-to-One)
- accounts.advito_business_owner -> owners.id (Many-to-One)
- accounts.me_business_owner -> owners.id (Many-to-One)
- accounts.bcd_business_owner -> owners.id (Many-to-One)
- accounts.latam_ram -> owners.id (Many-to-One)
- accounts.emea_ram -> owners.id (Many-to-One)
- accounts.apac_ram -> owners.id (Many-to-One)
- accounts.na_ram -> owners.id (Many-to-One)
- accounts.global_account_manager -> owners.id (Many-to-One)
- accounts.global_executive_sponsor -> owners.id (Many-to-One)
- accounts.id <- agreements.account_id (One-to-Many)
- accounts.id <- gcn.account_id (One-to-Many)

## Table: agreements

### Columns

- id (varchar(36), Primary Key, Default: uuid.uuid4())
- name (varchar(100))
- account_id (varchar(36), Foreign Key -> accounts.id)
- contract_type (enum: Single Country, Global, National Agreement, Multinational, Regional, Regional Agreement, Local Agreement)
- region (text)
- status (enum: Closed Consolidated, Lost, Pending Contract, Signed and Finalized, Servicing Without a Contract)
- effective_date (date)
- agreement_end_date (date)
- agreement_vp (varchar(36), Foreign Key -> owners.id)
- owner_id (varchar(36), Foreign Key -> owners.id)
- renewal_terms (enum: N/A, By Agreement Only, Automatic Renewal, Evergreen)

### Relationships

- agreements.account_id -> accounts.id (Many-to-One)
- agreements.owner_id -> owners.id (Many-to-One)
- agreements.agreement_vp -> owners.id (Many-to-One)
- agreements.id <- countries.agreement_id (One-to-Many)
- agreements.id <- annual_vol.agreement_id (One-to-Many)
- agreements.id <- program_sol.agreement_id (One-to-Many)

## Table: annual_vol

### Columns

- id (char(36), Primary Key, Default: uuid.uuid4())
- name (text)
- country_id (char(36), Foreign Key -> countries.id)
- agreement_id (char(36), Foreign Key -> agreements.id)
- air_transaction (integer)
- air_vol (numeric)
- train_transaction (integer)
- train_vol (numeric)
- car_transaction (integer)
- car_vol (numeric)
- currency_iso_code (char(5))

### Relationships

- annual_vol.country_id -> countries.id (Many-to-One)
- annual_vol.agreement_id -> agreements.id (Many-to-One)

## Table: countries

### Columns

- id (varchar(36), Primary Key, Default: uuid.uuid4())
- agreement_id (varchar(36), Foreign Key -> agreements.id, On Delete: CASCADE)
- name (text)
- region (text)
- agreement_status (text)
- country_status (enum: Implemented, In Scope, De-Implemented, Pending De-implementation, In Vetting)
- booking_country (text)
- ticket_country (text)

### Relationships

- countries.agreement_id -> agreements.id (Many-to-One)
- countries.id <- annual_vol.country_id (One-to-Many)
- countries.id <- program_sol.country_id (One-to-Many)

## Table: gcn

### Columns

- id (varchar(36), Primary Key, Default: uuid.uuid4())
- account_id (varchar(36), Foreign Key -> accounts.id, On Delete: CASCADE)
- status (enum: ZZ Archived, Active)
- client_name (text)
- case_number (text)
- is_me_gcn (boolean)
- client_exp_years (integer)

### Relationships

- gcn.account_id -> accounts.id (Many-to-One)

## Table: owner_permissions

### Columns

- owner_id (varchar(36), Primary Key, Foreign Key -> owners.id, On Delete: CASCADE)
- permission_id (varchar(36), Primary Key, Foreign Key -> permissions.id, On Delete: CASCADE)

### Relationships

- owner_permissions.owner_id -> owners.id (Many-to-One)
- owner_permissions.permission_id -> permissions.id (Many-to-One)

## Table: owners

### Columns

- id (varchar(36), Primary Key, Default: uuid.uuid4())
- name (text, Not Null)
- role (text, Not Null)
- alias (text, Not Null)
- license (text, Not Null)
- email (text, Unique, Not Null)
- email_status (boolean, Not Null)
- profile (text)
- username (text, Unique)
- company (enum: BCD Travel, Advito, EMEA, Not Null)
- time_zone (timestamp with time zone)
- division (text)
- locale (text)
- manager (text)
- mobile (varchar(10))
- last_login (timestamp)
- created_by (text)
- cost_center (numeric)
- user_division (enum: BCD Travel, Advito, EMEA, Not Null)
- ownership_type (text)
- me_sales_goal_usd (numeric)
- is_frozen (boolean, Not Null, Default: FALSE)
- created_at (timestamp, Not Null, Default: CURRENT_TIMESTAMP)

### Relationships

- owners.id <- accounts.owner_id (One-to-Many)
- owners.id <- accounts.national_svp (One-to-Many)
- owners.id <- accounts.hotel_sol_business_owner (One-to-Many)
- owners.id <- accounts.advito_business_owner (One-to-Many)
- owners.id <- accounts.me_business_owner (One-to-Many)
- owners.id <- accounts.bcd_business_owner (One-to-Many)
- owners.id <- accounts.latam_ram (One-to-Many)
- owners.id <- accounts.emea_ram (One-to-Many)
- owners.id <- accounts.apac_ram (One-to-Many)
- owners.id <- accounts.na_ram (One-to-Many)
- owners.id <- accounts.global_account_manager (One-to-Many)
- owners.id <- accounts.global_executive_sponsor (One-to-Many)
- owners.id <- agreements.owner_id (One-to-Many)
- owners.id <- agreements.agreement_vp (One-to-Many)
- owners.id <- owner_permissions.owner_id (One-to-Many)
- owners.id <- tool_service.product_marketer (One-to-Many)

## Table: permissions

### Columns

- id (varchar(36), Primary Key, Default: uuid.uuid4())
- name (text, Not Null)

### Relationships

- permissions.id <- owner_permissions.permission_id (One-to-Many)

## Table: program_sol

### Columns

- id (char(36), Primary Key, Default: uuid.uuid4())
- name (text)
- country_id (char(36), Foreign Key -> countries.id)
- product_type (text)
- status (enum: Implemented, De-Implemented, In Scope, In Vetting, Never Implemented)
- trial_exp_date (date)
- tool_service_id (char(36), Foreign Key -> tool_service.id)
- agreement_id (char(36), Foreign Key -> agreements.id)

### Relationships

- program_sol.country_id -> countries.id (Many-to-One)
- program_sol.tool_service_id -> tool_service.id (Many-to-One)
- program_sol.agreement_id -> agreements.id (Many-to-One)

## Table: tool_service

### Columns

- id (char(36), Primary Key, Default: uuid.uuid4())
- product_delivery (text)
- product_marketer (char(36), Foreign Key -> owners.id)
- product_category (text)
- name (text)
- tool_status (enum: Active, Inactive, In Development)
- availability_loc (enum: Ticketing, Booking, Customer)
- product_type (text)
- description (text)

### Relationships

- tool_service.product_marketer -> owners.id (Many-to-One)
- tool_service.id <- program_sol.tool_service_id (One-to-Many)
